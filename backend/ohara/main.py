"""Ohara web server: setup, sign-in, docs API, GitHub webhooks, and the React app."""

import asyncio
import functools
import json
import logging
import secrets
import time
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ohara import codeowners, config, db, docs, freshness, github, mcp_server, oauth, sessions, store

logging.basicConfig(level=logging.INFO, format="%(levelname)s:     %(message)s")
log = logging.getLogger("ohara")
SESSION_COOKIE = "ohara_session"
STATE_COOKIE = "ohara_state"
CONSENT_COOKIE = "ohara_consent"
sync_lock = asyncio.Lock()


async def sync() -> None:
    """Refresh repository metadata and replace the docs snapshot with the default branch."""
    async with sync_lock:
        settings = store.load()
        app, repo = settings.get("app"), settings.get("repo")
        if not app or not repo:
            return
        token = await github.installation_token(app, settings["installation_id"])
        repo = github.repo_summary(await github.get_repo(token, repo["full_name"]))
        store.update(repo=repo)
        data = await github.tarball(token, repo["full_name"], repo["default_branch"])
        await asyncio.to_thread(docs.extract, data, config.docs_dir())
        await asyncio.to_thread(docs.index, config.docs_dir())
        log.info("synced %s@%s", repo["full_name"], repo["default_branch"])


async def safe_sync() -> None:
    try:
        await sync()
    except Exception:
        log.exception("sync failed")


@asynccontextmanager
async def lifespan(_: FastAPI):
    if store.configured():
        await asyncio.to_thread(docs.index, config.docs_dir())  # search works even if GitHub is unreachable
        asyncio.create_task(safe_sync())
    async with mcp_server.run():
        yield


app = FastAPI(title="Ohara", lifespan=lifespan, docs_url=None, redoc_url=None)


def secure_cookies() -> bool:
    return config.base_url().startswith("https://")


def set_cookie(response, name: str, value: str, max_age: int | None = None) -> None:
    response.set_cookie(name, value, max_age=max_age, httponly=True, secure=secure_cookies(), samesite="lax")


async def viewer(request: Request, settings: dict) -> sessions.Session | None:
    return await sessions.current(request.cookies.get(SESSION_COOKIE), settings["app"], settings["repo"]["full_name"])


def can_read(settings: dict, session: sessions.Session | None) -> bool:
    """Public repository: open to everyone. Private: signed in and allowed to read the repository."""
    return not settings["repo"]["private"] or bool(session and session.allowed)


def require_configured() -> dict:
    settings = store.load()
    if not store.configured(settings):
        raise HTTPException(503, "Ohara is not configured")
    return settings


async def require_reader(request: Request, settings: dict = Depends(require_configured)) -> None:
    session = await viewer(request, settings) if settings["repo"]["private"] else None
    if not can_read(settings, session):
        raise HTTPException(403, "No access to the documentation repository") if session else HTTPException(401, "Sign in required")


def require_unconfigured() -> dict:
    if store.configured():
        raise HTTPException(409, "Ohara is already configured")
    return store.load()


# Status


@app.get("/api/status")
async def status(request: Request):
    settings = store.load()
    if not store.configured(settings):
        return {
            "configured": False,
            "url": config.base_url(),
            "install_url": github.install_url(settings["app"]) if settings.get("app") else None,
        }
    repo = settings["repo"]
    session = await viewer(request, settings)
    return {
        "configured": True,
        "repo": repo["full_name"],
        "branch": repo["default_branch"],
        "private": repo["private"],
        "user": {"login": session.login, "avatar": session.avatar} if session else None,
        "allowed": can_read(settings, session),
    }


# Setup: GitHub App manifest flow


@app.get("/api/setup/manifest", dependencies=[Depends(require_unconfigured)])
def setup_manifest(org: str = ""):
    state = secrets.token_urlsafe(24)
    store.update(setup_state=state)
    return {
        "action": f"{github.creation_url(org.strip() or None)}?state={state}",
        "manifest": json.dumps(github.manifest(config.base_url())),
    }


@app.get("/api/setup/callback")
async def setup_callback(code: str, state: str, settings: dict = Depends(require_unconfigured)):
    if not settings.get("setup_state") or not secrets.compare_digest(state, settings["setup_state"]):
        raise HTTPException(400, "Invalid setup state")
    app_credentials = await github.convert_manifest(code)
    store.update(app=app_credentials, setup_state=None)
    return RedirectResponse(github.install_url(app_credentials), 303)


@app.get("/api/setup/installed")
async def setup_installed(installation_id: int, settings: dict = Depends(require_unconfigured)):
    if not settings.get("app"):
        raise HTTPException(400, "Create the GitHub App first")
    await github.get_installation(settings["app"], installation_id)  # must belong to this app
    token = await github.installation_token(settings["app"], installation_id)
    repos = await github.installation_repos(token)
    if len(repos) != 1:
        return RedirectResponse(f"{config.base_path()}/setup?error=one-repository", 303)
    store.update(installation_id=installation_id, repo=github.repo_summary(repos[0]))
    await safe_sync()
    return RedirectResponse(f"{config.base_path()}/", 303)


# Sign-in


def safe_next(path: str) -> str:
    return path if path.startswith("/") and not path.startswith("//") else f"{config.base_path()}/"


@app.get("/api/auth/login")
def login(next: str = "/", mcp: str = "", settings: dict = Depends(require_configured)):
    """`mcp` carries a pending MCP client authorization, finished by the callback instead of a website session."""
    state = secrets.token_urlsafe(24)
    response = RedirectResponse(github.authorize_url(settings["app"], github.auth_callback_url(config.base_url()), state))
    set_cookie(response, STATE_COOKIE, json.dumps({"state": state, "next": safe_next(next), "mcp": mcp}), max_age=600)
    return response


@app.get("/api/auth/callback")
async def auth_callback(request: Request, code: str, state: str):
    settings = store.load()
    try:
        saved = json.loads(request.cookies.get(STATE_COOKIE, "{}"))
    except ValueError:
        saved = {}
    if not store.configured(settings) or not saved.get("state") or not secrets.compare_digest(state, saved["state"]):
        raise HTTPException(400, "Invalid sign-in state")
    app_credentials = settings["app"]
    try:
        tokens = await github.exchange_code(app_credentials, code, github.auth_callback_url(config.base_url()))
        user = await github.get_user(tokens["access_token"])
    except github.Unauthorized:
        raise HTTPException(400, "GitHub sign-in failed")
    sid = sessions.create(tokens, user)
    if saved.get("mcp"):
        if not oauth.describe(saved["mcp"]):
            sessions.drop(sid)
            raise HTTPException(400, "Authorization request expired, connect again from your coding assistant")
        session = await sessions.current(sid, app_credentials, settings["repo"]["full_name"])
        if not can_read(settings, session):
            response = RedirectResponse(oauth.complete(saved["mcp"], sid, "No access to the documentation repository"), 303)
        else:
            # The user approves the client on the consent page, in this browser only.
            consent = secrets.token_urlsafe(24)
            db.put("consent", consent, {"request": saved["mcp"], "session": sid, "login": user["login"]}, time.time() + oauth.PENDING_TTL)
            response = RedirectResponse(f"{config.base_path()}/oauth/consent", 303)
            set_cookie(response, CONSENT_COOKIE, consent, max_age=oauth.PENDING_TTL)
    else:
        response = RedirectResponse(safe_next(saved.get("next", "/")), 303)
        set_cookie(response, SESSION_COOKIE, sid, max_age=30 * 24 * 3600)
    response.delete_cookie(STATE_COOKIE)
    return response


def pending_consent(request: Request) -> tuple[str, dict]:
    consent = request.cookies.get(CONSENT_COOKIE, "")
    found = consent and db.get("consent", consent)
    if not found or not oauth.describe(found["request"]):
        raise HTTPException(404, "Authorization request expired, connect again from your coding assistant")
    return consent, found


@app.get("/api/auth/consent")
def consent_details(request: Request):
    _, found = pending_consent(request)
    return oauth.describe(found["request"]) | {"login": found["login"]}


class Answer(BaseModel):
    approve: bool


@app.post("/api/auth/consent")
def consent_answer(answer: Answer, request: Request):
    """The consent cookie is SameSite, so only a page on Ohara's own site can approve a client."""
    consent, found = pending_consent(request)
    redirect = db.pop("consent", consent) and oauth.complete(
        found["request"], found["session"], None if answer.approve else "The user denied access"
    )
    if not redirect:
        raise HTTPException(404, "Authorization request expired, connect again from your coding assistant")
    response = JSONResponse({"redirect": redirect})
    response.delete_cookie(CONSENT_COOKIE)
    return response


@app.post("/api/auth/logout")
def logout(request: Request):
    sessions.drop(request.cookies.get(SESSION_COOKIE))
    response = RedirectResponse(f"{config.base_path()}/", 303)
    response.delete_cookie(SESSION_COOKIE)
    return response


# Docs


@app.get("/api/nav", dependencies=[Depends(require_reader)])
def nav():
    root = config.docs_dir()
    return cached_nav(root, root.stat().st_ino) if root.exists() else []


@functools.lru_cache(maxsize=1)
def cached_nav(root, _snapshot: int) -> list[dict]:
    """Each sync swaps in a new snapshot folder, so its inode identifies the snapshot."""
    return docs.build_nav(root)


@app.get("/api/page", dependencies=[Depends(require_reader)])
def page(path: str = ""):
    found = docs.read_page(config.docs_dir(), path)
    if not found:
        raise HTTPException(404, "Page not found")
    return {key: found[key] for key in ("title", "file", "markdown")}


@app.get("/api/files/{path:path}", dependencies=[Depends(require_reader)])
def file(path: str):
    found = docs.resolve_file(config.docs_dir(), path)
    if not found:
        raise HTTPException(404, "File not found")
    return FileResponse(found, headers={"Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'"})


# GitHub webhooks


@app.post("/api/github/webhook")
async def webhook(request: Request, background: BackgroundTasks):
    """Pushes to the docs repository rebuild the site. Pushes to other repositories the app is
    installed on flag the pages that cover the changed code, and their merged or closed pull requests
    merge or close the docs pull request of the same branch."""
    settings = store.load()
    body = await request.body()
    secret = (settings.get("app") or {}).get("webhook_secret")
    if not secret or not github.valid_signature(secret, body, request.headers.get("X-Hub-Signature-256")):
        raise HTTPException(401, "Invalid signature")
    repo = settings.get("repo")
    payload = json.loads(body)
    event = request.headers.get("X-GitHub-Event")
    source = payload.get("repository") or {}
    if not repo or not source.get("full_name"):
        return {"synced": False}
    if source["full_name"] != repo["full_name"]:
        if event == "push" and payload.get("ref") == f"refs/heads/{source.get('default_branch')}" and payload.get("installation"):
            background.add_task(safe_check_code, payload)
            return {"synced": False, "checked": True}
        closed = event == "pull_request" and payload.get("action") == "closed" and payload.get("installation")
        if closed and payload["pull_request"]["base"]["ref"] == source.get("default_branch"):
            background.add_task(safe_follow_code, payload)
            return {"synced": False, "followed": True}
        return {"synced": False}
    pushed_default = event == "push" and payload.get("ref") == f"refs/heads/{repo['default_branch']}"
    if pushed_default or event == "repository":
        background.add_task(safe_sync)
        return {"synced": True}
    return {"synced": False}


async def check_code(payload: dict) -> None:
    """Flag the docs pages that cover code changed by a push."""
    settings = store.load()
    full_name, before, after = payload["repository"]["full_name"], payload["before"], payload["after"]
    if set(before) == {"0"}:  # a new branch: no previous commit to compare with
        files = sorted({name for commit in payload.get("commits", []) for key in ("added", "modified", "removed") for name in commit.get(key, [])})
    else:
        token = await github.installation_token(settings["app"], payload["installation"]["id"])
        files = await github.changed_files(token, full_name, before, after)
    compare = f"https://github.com/{full_name}/compare/{before[:12]}...{after[:12]}"
    flagged = await asyncio.to_thread(freshness.record_push, config.docs_dir(), full_name, files, compare)
    if flagged:
        log.info("code change in %s flagged %s", full_name, ", ".join(flagged))


async def safe_check_code(payload: dict) -> None:
    try:
        await check_code(payload)
    except Exception:
        log.exception("code change check failed")


async def follow_code(payload: dict) -> None:
    """When a code pull request is merged, merge the docs pull request of its branch if no page in it has code
    owners. When it is closed without merging, close that docs pull request."""
    settings = store.load()
    docs_repo = settings["repo"]["full_name"]
    code = payload["pull_request"]
    branch = mcp_server.code_branch(payload["repository"]["name"], code["head"]["ref"])
    if not branch:
        return
    token = await github.installation_token(settings["app"], settings["installation_id"])
    pull = await github.find_pull(token, docs_repo, branch)
    if not pull:
        return
    if not code.get("merged"):
        await github.comment(token, docs_repo, pull["number"], f"Closed: {code['html_url']} was closed without merging.")
        await github.close_pull(token, docs_repo, pull["number"])
        return
    files = await github.pull_files(token, docs_repo, pull["number"])
    rules = codeowners.load(config.docs_dir())
    owned = [file for file in files if codeowners.needs_review(rules, file)]
    if owned:
        why = "have code owners and need review" if rules is not None else "need review: the docs repository has no CODEOWNERS file"
        reason = f"{code['html_url']} was merged, but these files {why}: {', '.join(owned)}"
    else:
        refused = await github.merge_pull(token, docs_repo, pull["number"], pull["head"]["sha"])
        if not refused:
            log.info("merged %s with %s", pull["html_url"], code["html_url"])
            return
        reason = f"{code['html_url']} was merged, but this pull request could not merge: {refused}"
    await github.comment(token, docs_repo, pull["number"], reason)


async def safe_follow_code(payload: dict) -> None:
    try:
        await follow_code(payload)
    except Exception:
        log.exception("docs pull request follow-up failed")


# MCP server


app.router.add_route("/mcp", mcp_server.app, methods=["GET", "POST", "DELETE"], include_in_schema=False)
app.router.routes.extend(mcp_server.oauth_routes())


# React app


static = config.static_dir()
if (static / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=static / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(404)
        candidate = (static / path).resolve()
        if path and candidate.is_relative_to(static.resolve()) and candidate.is_file():
            return FileResponse(candidate)
        return HTMLResponse(index_html())


@functools.cache
def index_html() -> str:
    """The React app's page, with its assets and routes moved under the base path."""
    base = config.base_path()
    html = (static / "index.html").read_text().replace('="./', f'="{base}/')
    return html.replace("<head>", f'<head>\n    <meta name="ohara-base" content="{base}" />', 1)


class BasePath:
    """Serve Ohara under the path of OHARA_URL, such as https://acme.com/docs, and send the rest of the host there.

    OAuth discovery stays at the host's root, as clients look for it there (RFC 8414 and RFC 9728).
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        base = config.base_path()
        if scope["type"] != "http" or not base:
            return await self.app(scope, receive, send)
        path = scope["path"]
        if path == f"{AUTH_METADATA}{base}":
            path = f"{base}{AUTH_METADATA}"
        if path.startswith(f"{base}/"):
            return await self.app({**scope, "path": path, "root_path": base}, receive, send)
        if path.startswith(f"{RESOURCE_METADATA}{base}/"):
            return await self.app(scope, receive, send)
        if scope["method"] in ("GET", "HEAD"):
            query = scope["query_string"].decode()
            target = f"{base}/" if path in ("/", base) else f"{base}{path}"
            return await RedirectResponse(f"{target}?{query}" if query else target, 308)(scope, receive, send)
        await PlainTextResponse("Not found", 404)(scope, receive, send)


AUTH_METADATA = "/.well-known/oauth-authorization-server"
RESOURCE_METADATA = "/.well-known/oauth-protected-resource"
app.add_middleware(BasePath)
