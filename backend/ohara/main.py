"""Ohara web server: setup, sign-in, docs API, GitHub webhooks, and the React app."""

import asyncio
import functools
import json
import logging
import secrets
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.types import ASGIApp, Receive, Scope, Send

from ohara import appdocs, config, db, docs, freshness, github, mcp_server, oauth, sessions, store

logging.basicConfig(level=logging.INFO, format="%(levelname)s:     %(message)s")
log = logging.getLogger("ohara")
SESSION_COOKIE = "ohara_session"
STATE_COOKIE = "ohara_state"
CONSENT_COOKIE = "ohara_consent"
SETUP_TTL = 600  # seconds to come back from GitHub with the new app
SIGN_IN_TTL = 600  # seconds to come back from the GitHub sign-in
AUTH_METADATA = "/.well-known/oauth-authorization-server"
RESOURCE_METADATA = "/.well-known/oauth-protected-resource"
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


async def startup() -> None:
    await safe_sync()
    await safe_backfill()


async def backfill() -> None:
    """Sync the docs of every code repository on the installation, so changes to the sync rules apply to all of them,
    and remove the synced folders of repositories that are no longer on it."""
    settings = store.load()
    token = await github.installation_token(settings["app"], settings["installation_id"])
    repos = [repo for repo in await github.installation_repos(token) if repo["full_name"] != settings["repo"]["full_name"]]
    for repo in repos:
        await appdocs.sync(settings, repo["full_name"])
    owner = settings["repo"]["full_name"].split("/")[0]
    for name in appdocs.orphans(config.docs_dir(), {repo["name"] for repo in repos}):
        await appdocs.remove(settings, f"{owner}/{name}")


async def safe_backfill() -> None:
    try:
        await backfill()
    except Exception:
        log.exception("app docs backfill failed")


async def safe_sync_app(full_name: str, ref: str | None = None) -> None:
    try:
        await appdocs.sync(store.load(), full_name, ref)
    except Exception:
        log.exception("app docs sync of %s failed", full_name)


async def safe_remove_app(full_name: str) -> None:
    try:
        await appdocs.remove(store.load(), full_name)
    except Exception:
        log.exception("removing the app docs of %s failed", full_name)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    if store.configured():
        await asyncio.to_thread(docs.index, config.docs_dir())  # search works even if GitHub is unreachable
        asyncio.create_task(startup())
    async with mcp_server.run():
        yield
    await github.close()


app = FastAPI(title="Ohara", lifespan=lifespan, docs_url=None, redoc_url=None)


def secure_cookies() -> bool:
    return config.base_url().startswith("https://")


def set_cookie(response: Response, name: str, value: str, max_age: int | None = None) -> None:
    response.set_cookie(name, value, max_age=max_age, httponly=True, secure=secure_cookies(), samesite="lax")


async def viewer(request: Request, response: Response, settings: dict) -> sessions.Session | None:
    """Each use renews the session cookie, so a session ends only after `sessions.TTL` without use."""
    sid = request.cookies.get(SESSION_COOKIE)
    session = await sessions.current(sid, settings["app"], settings["repo"]["full_name"])
    if session:
        set_cookie(response, SESSION_COOKIE, sid, max_age=sessions.TTL)
    return session


def can_read(settings: dict, session: sessions.Session | None) -> bool:
    """Public repository: open to everyone. Private: signed in and allowed to read the repository."""
    return not settings["repo"]["private"] or bool(session and session.allowed)


def require_configured() -> dict:
    settings = store.load()
    if not store.configured(settings):
        raise HTTPException(503, "Ohara is not set up yet: an admin finishes setup on the setup page")
    return settings


async def require_reader(request: Request, response: Response, settings: dict = Depends(require_configured)) -> None:
    session = await viewer(request, response, settings) if settings["repo"]["private"] else None
    if not can_read(settings, session):
        raise HTTPException(403, sessions.NO_ACCESS) if session else HTTPException(401, "Sign in with GitHub to read the documentation")


def require_unconfigured() -> dict:
    if store.configured():
        raise HTTPException(409, "Ohara is already configured")
    return store.load()


# Status


@app.get("/api/status")
async def status(request: Request, response: Response) -> dict:
    settings = store.load()
    if not store.configured(settings):
        return {
            "configured": False,
            "url": config.base_url(),
            "install_url": github.install_url(settings["app"]) if settings.get("app") else None,
            "installed": bool(settings.get("installation_id")),
        }
    repo = settings["repo"]
    session = await viewer(request, response, settings)
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
def setup_manifest(org: str = "") -> dict[str, str]:
    state = secrets.token_urlsafe(24)
    db.put("setup", state, True, time.time() + SETUP_TTL)
    return {
        "action": f"{github.creation_url(org.strip() or None)}?state={state}",
        "manifest": json.dumps(github.manifest(config.base_url())),
    }


@app.get("/api/setup/callback")
async def setup_callback(code: str, state: str, settings: dict = Depends(require_unconfigured)) -> RedirectResponse:
    """Each state works once: popping it means two callbacks can't both create an app."""
    if not db.pop("setup", state):
        raise HTTPException(400, "This setup link expired or was already used, start setup again from the setup page")
    app_credentials = await github.convert_manifest(code)
    store.update(app=app_credentials)
    return RedirectResponse(github.install_url(app_credentials), 303)


def require_app() -> dict:
    settings = store.load()
    if not settings.get("app"):
        raise HTTPException(400, "Create the GitHub App first, from the setup page")
    return settings


@app.get("/api/setup/installed")
async def setup_installed(installation_id: int | None = None, settings: dict = Depends(require_app)) -> RedirectResponse:
    """GitHub redirects here after an install or a change of repositories; without an id, the setup page checks again.
    Once Ohara is configured, an admin who added a code repository returns to the website."""
    if store.configured(settings):
        return RedirectResponse(f"{config.base_path()}/", 303)
    if installation_id is None:
        # The app is private, so it has at most one installation: on the account that owns it.
        installations = await github.app_installations(settings["app"])
        if not installations:
            return RedirectResponse(f"{config.base_path()}/setup", 303)
        installation_id = installations[0]["id"]
    else:
        await github.get_installation(settings["app"], installation_id)  # must belong to this app
    store.update(installation_id=installation_id)
    repos = await installed_repos(settings["app"], installation_id)
    if len(repos) == 1:
        await choose_repository(repos[0])
        return RedirectResponse(f"{config.base_path()}/", 303)
    return RedirectResponse(f"{config.base_path()}/setup", 303)


async def installed_repos(app_credentials: dict, installation_id: int) -> list[dict]:
    token = await github.installation_token(app_credentials, installation_id)
    return await github.installation_repos(token)


async def choose_repository(repo: dict) -> None:
    store.update(repo=github.repo_summary(repo))
    await safe_sync()


def require_installed(settings: dict = Depends(require_unconfigured)) -> dict:
    if not settings.get("app") or not settings.get("installation_id"):
        raise HTTPException(400, "Install the GitHub App first, from the setup page")
    return settings


@app.get("/api/setup/repositories")
async def setup_repositories(settings: dict = Depends(require_installed)) -> list[dict]:
    """The repositories the app is installed on, for the admin to choose the docs repository."""
    repos = await installed_repos(settings["app"], settings["installation_id"])
    return sorted(({"full_name": r["full_name"], "private": r["private"]} for r in repos), key=lambda r: r["full_name"].lower())


class Choice(BaseModel):
    full_name: str


@app.post("/api/setup/repository")
async def setup_repository(choice: Choice, settings: dict = Depends(require_installed)) -> dict[str, str]:
    repos = await installed_repos(settings["app"], settings["installation_id"])
    repo = next((r for r in repos if r["full_name"] == choice.full_name), None)
    if not repo:
        raise HTTPException(400, "The app isn't installed on this repository: add it to the installation on GitHub, or pick another")
    await choose_repository(repo)
    return {"repo": repo["full_name"]}


# Sign-in


def safe_next(path: str) -> str:
    return path if path.startswith("/") and not path.startswith("//") else f"{config.base_path()}/"


@app.get("/api/auth/login")
def login(next: str = "/", mcp: str = "", settings: dict = Depends(require_configured)) -> RedirectResponse:
    """`mcp` carries a pending MCP client authorization, finished by the callback instead of a website session."""
    state = secrets.token_urlsafe(24)
    response = RedirectResponse(github.authorize_url(settings["app"], github.auth_callback_url(config.base_url()), state))
    set_cookie(response, STATE_COOKIE, json.dumps({"state": state, "next": safe_next(next), "mcp": mcp}), max_age=SIGN_IN_TTL)
    return response


@app.get("/api/auth/callback")
async def auth_callback(request: Request, state: str, code: str = "") -> RedirectResponse:
    """Without a code, the user cancelled on GitHub: return to the page, or deny the MCP client."""
    settings = store.load()
    try:
        saved = json.loads(request.cookies.get(STATE_COOKIE, "{}"))
    except ValueError:
        saved = {}
    if not store.configured(settings) or not saved.get("state") or not secrets.compare_digest(state, saved["state"]):
        raise HTTPException(400, "This sign-in link expired or was already used: sign in again")
    if not code:
        if saved.get("mcp"):
            denied = oauth.complete(saved["mcp"], None, "The user cancelled the GitHub sign-in")
            if not denied:
                raise HTTPException(400, "Authorization request expired, connect again from your coding assistant")
            response = RedirectResponse(denied, 303)
        else:
            response = RedirectResponse(safe_next(saved.get("next", "/")), 303)
        response.delete_cookie(STATE_COOKIE)
        return response
    app_credentials = settings["app"]
    try:
        tokens = await github.exchange_code(app_credentials, code, github.auth_callback_url(config.base_url()))
        user = await github.get_user(tokens["access_token"])
    except github.Unauthorized:
        raise HTTPException(400, "GitHub sign-in failed: sign in again")
    sid = sessions.create(tokens, user)
    if saved.get("mcp"):
        if not oauth.describe(saved["mcp"]):
            sessions.drop(sid)
            raise HTTPException(400, "Authorization request expired, connect again from your coding assistant")
        session = await sessions.current(sid, app_credentials, settings["repo"]["full_name"])
        if not can_read(settings, session):
            response = RedirectResponse(oauth.complete(saved["mcp"], sid, sessions.NO_ACCESS), 303)
        else:
            # The user approves the client on the consent page, in this browser only.
            consent = secrets.token_urlsafe(24)
            db.put("consent", consent, {"request": saved["mcp"], "session": sid, "login": user["login"]}, time.time() + oauth.PENDING_TTL)
            response = RedirectResponse(f"{config.base_path()}/oauth/consent", 303)
            set_cookie(response, CONSENT_COOKIE, consent, max_age=oauth.PENDING_TTL)
    else:
        response = RedirectResponse(safe_next(saved.get("next", "/")), 303)
        set_cookie(response, SESSION_COOKIE, sid, max_age=sessions.TTL)
    response.delete_cookie(STATE_COOKIE)
    return response


def pending_consent(request: Request) -> tuple[str, dict]:
    consent = request.cookies.get(CONSENT_COOKIE, "")
    found = consent and db.get("consent", consent)
    if not found or not oauth.describe(found["request"]):
        raise HTTPException(404, "Authorization request expired, connect again from your coding assistant")
    return consent, found


@app.get("/api/auth/consent")
def consent_details(pending: tuple[str, dict] = Depends(pending_consent)) -> dict:
    _, found = pending
    return oauth.describe(found["request"]) | {"login": found["login"]}


class Answer(BaseModel):
    approve: bool


@app.post("/api/auth/consent")
def consent_answer(answer: Answer, pending: tuple[str, dict] = Depends(pending_consent)) -> JSONResponse:
    """The consent cookie is SameSite, so only a page on Ohara's own site can approve a client."""
    consent, found = pending
    redirect = db.pop("consent", consent) and oauth.complete(
        found["request"], found["session"], None if answer.approve else "The user denied access"
    )
    if not redirect:
        raise HTTPException(404, "Authorization request expired, connect again from your coding assistant")
    response = JSONResponse({"redirect": redirect})
    response.delete_cookie(CONSENT_COOKIE)
    return response


@app.post("/api/auth/logout")
def logout(request: Request) -> RedirectResponse:
    sessions.drop(request.cookies.get(SESSION_COOKIE))
    response = RedirectResponse(f"{config.base_path()}/", 303)
    response.delete_cookie(SESSION_COOKIE)
    return response


# Docs


@app.get("/api/nav", dependencies=[Depends(require_reader)])
def nav() -> list[dict]:
    root = config.docs_dir()
    return cached_nav(root, root.stat().st_ino) if root.exists() else []


@functools.lru_cache(maxsize=1)
def cached_nav(root: Path, _snapshot: int) -> list[dict]:
    """Each sync swaps in a new snapshot folder, so its inode identifies the snapshot."""
    return docs.build_nav(root)


@app.get("/api/page", dependencies=[Depends(require_reader)])
def page(path: str = "") -> dict:
    found = docs.read_page(config.docs_dir(), path)
    if not found:
        raise HTTPException(404, "Page not found")
    return {key: found[key] for key in ("title", "file", "markdown")} | {"source": source_of(found)}


def source_of(page: dict) -> dict | None:
    """Where a synced page lives in its code repository, for the website's edit link."""
    repo, _, path = str(page["meta"].get("source") or "").partition(":")
    if not appdocs.synced(page["file"]) or not repo or not path:
        return None
    branch = (appdocs.state(repo) or {}).get("branch") or "HEAD"
    return {"repo": repo, "path": path, "edit_url": f"{github.WEB}/{repo}/edit/{branch}/{path}"}


@app.get("/api/files/{path:path}", dependencies=[Depends(require_reader)])
def file(path: str) -> FileResponse:
    found = docs.resolve_file(config.docs_dir(), path)
    if not found:
        raise HTTPException(404, "File not found")
    return FileResponse(found, headers={"Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'"})


# GitHub webhooks


@app.post("/api/github/webhook")
async def webhook(request: Request, background: BackgroundTasks) -> dict:
    """Pushes to the docs repository rebuild the site. Pushes to other repositories the app is
    installed on flag the pages that cover the changed code."""
    settings = store.load()
    body = await request.body()
    secret = (settings.get("app") or {}).get("webhook_secret")
    if not secret or not github.valid_signature(secret, body, request.headers.get("X-Hub-Signature-256")):
        raise HTTPException(401, "Invalid signature: check the webhook secret of the GitHub App")
    repo = settings.get("repo")
    payload = json.loads(body)
    event = request.headers.get("X-GitHub-Event")
    if repo and event == "installation_repositories" and payload.get("installation", {}).get("id") == settings.get("installation_id"):
        for added in payload.get("repositories_added", []):
            background.add_task(safe_sync_app, added["full_name"])
        for removed in payload.get("repositories_removed", []):
            background.add_task(safe_remove_app, removed["full_name"])
        return {"synced": False, "apps": True}
    source = payload.get("repository") or {}
    if not repo or not source.get("full_name"):
        return {"synced": False}
    if source["full_name"] != repo["full_name"]:
        if event == "push" and payload.get("ref") == f"refs/heads/{source.get('default_branch')}" and payload.get("installation"):
            background.add_task(safe_check_code, payload)
            return {"synced": False, "checked": True}
        return {"synced": False}
    pushed_default = event == "push" and payload.get("ref") == f"refs/heads/{repo['default_branch']}"
    if pushed_default:
        for full_name in appdocs.touched_by_hand(payload, settings):
            background.add_task(safe_sync_app, full_name)
    if pushed_default or event == "repository":
        background.add_task(safe_sync)
        if event == "repository" and payload.get("action") == "publicized":
            for full_name in db.all("app"):  # private code repositories must leave the now public docs
                background.add_task(safe_sync_app, full_name)
        return {"synced": True}
    return {"synced": False}


async def check_code(payload: dict) -> None:
    """Sync the app docs a push changed, and flag the docs pages that cover the changed code."""
    settings = store.load()
    full_name, before, after = payload["repository"]["full_name"], payload["before"], payload["after"]
    if set(before) == {"0"}:  # a new branch: no previous commit to compare with
        commits = payload.get("commits", [])
        files = sorted({name for commit in commits for key in ("added", "modified", "removed") for name in commit.get(key, [])})
    else:
        token = await github.installation_token(settings["app"], payload["installation"]["id"])
        files = await github.changed_files(token, full_name, before, after)
    if appdocs.needs_sync(full_name, files):
        await safe_sync_app(full_name, after)
    compare = f"{github.WEB}/{full_name}/compare/{before[:12]}...{after[:12]}"
    flagged = await asyncio.to_thread(freshness.record_push, config.docs_dir(), full_name, files, compare)
    if flagged:
        log.info("code change in %s flagged %s", full_name, ", ".join(flagged))


async def safe_check_code(payload: dict) -> None:
    try:
        await check_code(payload)
    except Exception:
        log.exception("code change check failed")


# MCP server


app.router.add_route("/mcp", mcp_server.app, methods=["GET", "POST", "DELETE"], include_in_schema=False)
app.router.routes.extend(mcp_server.oauth_routes())


# React app


static = config.static_dir()
if (static / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=static / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> Response:
        if path.startswith("api/"):
            raise HTTPException(404, "No such API route: check the path")
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

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
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


app.add_middleware(BasePath)
