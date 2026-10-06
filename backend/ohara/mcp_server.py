"""MCP server for AI agents and coding assistants, served at /mcp.

Access mirrors the website: a public docs repository is open to everyone. A private
one requires a bearer token: an Ohara token from the OAuth sign-in (see oauth.py), or a
GitHub token for CI and headless agents. Repository access is re-checked with GitHub
every 5 minutes.

Agents read pages and propose changes. A proposal becomes a pull request on the docs
repository, opened by the GitHub App, and a human reviews and merges it. Proposing
requires a signed-in user who can write to the repository. Pages report their freshness
(see freshness.py), so agents know which ones to bring up to date.
"""

import datetime
import hashlib
import logging
import re
import secrets
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass

import httpx
from mcp.server.mcpserver import Context
from pydantic import BaseModel

from mcp.server.auth.routes import create_auth_routes, create_protected_resource_routes
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.responses import JSONResponse

from ohara import config, db, docs, freshness, github, oauth, sessions, store
from ohara.sessions import CHECK_INTERVAL

SEARCH_LIMIT = 20

server = MCPServer(
    "Ohara",
    instructions=(
        "Ohara holds the enterprise documentation and engineering guidelines. "
        "Treat it as the source of truth: search or list pages, then read the ones relevant to the task. "
        "When the documentation is wrong or missing something, propose a change for a human to review."
    ),
)


@server.tool()
def list_pages() -> list[dict]:
    """List every documentation page with its path and title."""
    root = config.docs_dir()
    pages = []

    def walk(nodes: list[dict], parents: list[str]) -> None:
        for node in nodes:
            if node["path"] is not None:
                pages.append({"path": node["path"], "title": " / ".join([*parents, node["title"]])})
            walk(node["children"], [*parents, node["title"]])

    walk(docs.build_nav(root) if root.exists() else [], [])
    return pages


class Page(BaseModel):
    title: str
    markdown: str
    owner: str | None
    verified: str | None
    stale: list[str]


@server.tool()
def read_page(path: str) -> Page:
    """Read a documentation page as Markdown. Use a path from list_pages or search; an empty path is the home page.

    Also returns the page's owner, the date a human last verified it, and why it may be stale.
    Tell the user when a page you rely on is stale.
    """
    root = config.docs_dir()
    found = docs.read_page(root, path)
    if not found:
        raise ValueError(f"Page not found: {path}")
    return Page(title=found["title"], markdown=found["markdown"], **freshness.status(root, found))


@server.tool()
def search(query: str) -> list[dict]:
    """Find documentation pages that contain every word of the query, best matches first."""
    root = config.docs_dir()
    results = docs.search(query, SEARCH_LIMIT)
    for result in results:
        found = docs.read_page(root, result["path"])
        result["stale"] = freshness.status(root, found)["stale"] if found else []
    return results


@server.tool()
def stale_pages() -> list[dict]:
    """List the pages that may be out of date, with the reasons: not verified for a long time,
    or code they describe changed since. Read each one and propose a change to bring it up to date."""
    return freshness.stale_pages(config.docs_dir())


class PageChange(BaseModel):
    path: str
    markdown: str


@server.tool()
async def propose_change(title: str, description: str, pages: list[PageChange], ctx: Context) -> str:
    """Propose documentation changes as a pull request for a human to review and merge.

    Each page has a path, from list_pages or a new one such as "team/onboarding", and its full new Markdown,
    front matter included. Ohara sets the page's `verified` date, so merging the change verifies the page.
    The title and description explain the change to the reviewer. Returns the pull request URL.
    """
    caller: Caller | None = ctx.request_context.request.state.caller
    if not caller:
        raise ValueError("Sign in required: connect with a GitHub token that can write to the docs repository")
    settings = store.load()
    repo = settings["repo"]
    try:
        login = caller.login or (await github.get_user(caller.github_token))["login"]
        can_write = await github.user_can_write(caller.github_token, repo["full_name"], login)
    except github.Unauthorized:
        raise ValueError("Sign in again: the GitHub token is no longer valid")
    if not can_write:
        raise ValueError("Proposing changes requires write access to the docs repository")
    today = datetime.date.today()
    files = {file_for(page.path): freshness.stamp_verified(page.markdown, today) for page in pages}
    if not files:
        raise ValueError("No pages to change")
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40] or "change"
    body = f"{description}\n\n---\nProposed through Ohara by @{login}."
    try:
        token = await github.installation_token(settings["app"], settings["installation_id"])
        return await github.open_pull_request(
            token, repo["full_name"], repo["default_branch"], f"ohara/{slug}-{secrets.token_hex(3)}", files, title, body
        )
    except httpx.HTTPStatusError as error:
        if error.response.status_code == 403:
            raise ValueError(
                "The Ohara GitHub App cannot write to the docs repository. An admin must grant it "
                "Contents and Pull requests write permissions in the app settings, then accept them on the installation."
            )
        raise


def file_for(path: str) -> str:
    """The repository file of a page path: the existing file, or a new Markdown file."""
    path = path.strip().strip("/").removesuffix(".md")
    found = docs.read_page(config.docs_dir(), path)
    if found:
        return found["file"]
    parts = path.split("/")
    if not path or any(not part or part.startswith(".") for part in parts):
        raise ValueError(f"Invalid page path: {path!r}")
    return f"{path}.md"


_handler = None


@asynccontextmanager
async def run():
    """Start a fresh MCP transport for the web server's lifetime."""
    global _handler
    # Bearer tokens replace cookies here, so DNS rebinding protection has nothing to guard.
    http = server.streamable_http_app(
        stateless_http=True,
        json_response=True,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    _handler = next(route.endpoint for route in http.routes if route.path == "/mcp")
    async with server.session_manager.run():
        yield


def oauth_routes() -> list:
    """OAuth discovery, registration, authorization, token and revocation endpoints."""
    try:
        # AuthSettings keeps the issuer without a trailing slash, as clients compare it exactly.
        urls = AuthSettings(issuer_url=config.base_url(), resource_server_url=oauth.resource_url(), validate_token_resource=False)
        base = urls.issuer_url
        return [
            *create_auth_routes(
                oauth.provider,
                issuer_url=base,
                client_registration_options=ClientRegistrationOptions(enabled=True),
                revocation_options=RevocationOptions(enabled=True),
            ),
            *create_protected_resource_routes(urls.resource_server_url, [base], resource_name="Ohara"),
        ]
    except ValueError as error:  # OAuth requires HTTPS outside localhost
        logging.getLogger("ohara").warning("MCP sign-in disabled: %s", error)
        return []


@dataclass
class Caller:
    allowed: bool  # can read the docs repository
    github_token: str
    login: str | None = None


async def authenticate(token: str, settings: dict) -> Caller | None:
    """Who sends this bearer token, or None when the token is invalid or expired."""
    repo = settings["repo"]["full_name"]
    if token.startswith(oauth.PREFIX):
        access = await oauth.provider.load_access_token(token)
        if not access or access.resource and access.resource.rstrip("/") != oauth.resource_url():
            return None
        session = await sessions.current(access.session, settings["app"], repo)
        return Caller(session.allowed, session.token, session.login) if session else None
    key = hashlib.sha256(f"{repo}:{token}".encode()).hexdigest()
    checked = db.get("check", key)
    if checked is None:
        try:
            checked = await github.user_can_read(token, repo)
        except github.Unauthorized:
            return None
        db.put("check", key, checked, time.time() + CHECK_INTERVAL)
    return Caller(checked, token)


class App:
    """ASGI app for /mcp. A class, so Starlette routes raw ASGI calls to it."""

    async def __call__(self, scope, receive, send) -> None:
        await guarded(scope, receive, send)


async def guarded(scope, receive, send) -> None:
    settings = store.load()
    if not store.configured(settings):
        return await JSONResponse({"detail": "Ohara is not configured"}, 503)(scope, receive, send)
    header = dict(scope["headers"]).get(b"authorization", b"").decode()
    token = header[7:].strip() if header[:7].lower() == "bearer " else ""
    caller = await authenticate(token, settings) if token else None
    if (token and not caller) or (settings["repo"]["private"] and not (caller and caller.allowed)):
        status, detail = (403, "No access to the documentation repository") if caller else (401, "Sign in required")
        metadata = f"{config.base_url()}/.well-known/oauth-protected-resource/mcp"
        headers = {"WWW-Authenticate": f'Bearer resource_metadata="{metadata}"'} if status == 401 else None
        return await JSONResponse({"detail": detail}, status, headers=headers)(scope, receive, send)
    scope["state"] = {**scope.get("state", {}), "caller": caller}  # a copy, so requests never share it
    await _handler(scope, receive, send)


app = App()
