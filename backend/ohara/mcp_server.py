"""MCP server for AI agents and coding assistants, served at /mcp.

Access mirrors the website: a public docs repository is open to everyone. A private
one requires a bearer token: an Ohara token from the OAuth sign-in (see oauth.py), or a
GitHub token for CI and headless agents. Repository access is re-checked with GitHub
every 5 minutes.
"""

import hashlib
import logging
import time
from contextlib import asynccontextmanager

from mcp.server.auth.routes import create_auth_routes, create_protected_resource_routes
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.responses import JSONResponse

from ohara import config, docs, github, oauth, sessions, store
from ohara.sessions import CHECK_INTERVAL

SEARCH_LIMIT = 20

server = MCPServer(
    "Ohara",
    instructions=(
        "Ohara holds the enterprise documentation and engineering guidelines. "
        "Treat it as the source of truth: search or list pages, then read the ones relevant to the task."
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


@server.tool()
def read_page(path: str) -> str:
    """Read a documentation page as Markdown. Use a path from list_pages or search; an empty path is the home page."""
    found = docs.read_page(config.docs_dir(), path)
    if not found:
        raise ValueError(f"Page not found: {path}")
    return found["markdown"]


@server.tool()
def search(query: str) -> list[dict]:
    """Find documentation pages whose title or text contains every word of the query."""
    root = config.docs_dir()
    words = query.lower().split()
    if not words or not root.exists():
        return []
    results = []
    for file in sorted(root.rglob("*.md")):
        rel = file.relative_to(root)
        if any(part.startswith(".") for part in rel.parts):
            continue
        _, body, title = docs.page_info(file)
        text = f"{title}\n{body}".lower()
        if all(word in text for word in words):
            path = rel.as_posix()[:-3]
            if rel.name in docs.INDEX_NAMES:
                path = rel.parent.as_posix().removeprefix(".")
            body = " ".join(docs.HEADING.sub("", body, count=1).split())
            at = max(0, body.lower().find(words[0]))
            snippet = body[max(0, at - 80) : at + 160]
            results.append({"path": path, "title": title, "snippet": snippet})
            if len(results) == SEARCH_LIMIT:
                break
    return results


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


checks: dict[str, tuple[bool, float]] = {}


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


async def token_can_read(token: str, settings: dict) -> bool | None:
    """Whether the token can read the repository, or None when the token is invalid or expired."""
    repo = settings["repo"]["full_name"]
    if token.startswith(oauth.PREFIX):
        access = await oauth.provider.load_access_token(token)
        if not access or access.resource and access.resource.rstrip("/") != oauth.resource_url():
            return None
        session = await sessions.current(access.session, settings["app"], repo)
        return session.allowed if session else None
    key = hashlib.sha256(f"{repo}:{token}".encode()).hexdigest()
    allowed, checked_at = checks.get(key, (False, 0.0))
    if time.time() - checked_at < CHECK_INTERVAL:
        return allowed
    try:
        allowed = await github.user_can_read(token, repo)
    except github.Unauthorized:
        checks.pop(key, None)
        return None
    checks[key] = (allowed, time.time())
    return allowed


class App:
    """ASGI app for /mcp. A class, so Starlette routes raw ASGI calls to it."""

    async def __call__(self, scope, receive, send) -> None:
        await guarded(scope, receive, send)


async def guarded(scope, receive, send) -> None:
    settings = store.load()
    if not store.configured(settings):
        return await JSONResponse({"detail": "Ohara is not configured"}, 503)(scope, receive, send)
    repo = settings["repo"]
    if repo["private"]:
        header = dict(scope["headers"]).get(b"authorization", b"").decode()
        token = header[7:].strip() if header[:7].lower() == "bearer " else ""
        allowed = await token_can_read(token, settings) if token else None
        if not allowed:
            status, detail = (403, "No access to the documentation repository") if allowed is False else (401, "Sign in required")
            metadata = f"{config.base_url()}/.well-known/oauth-protected-resource/mcp"
            headers = {"WWW-Authenticate": f'Bearer resource_metadata="{metadata}"'} if status == 401 else None
            return await JSONResponse({"detail": detail}, status, headers=headers)(scope, receive, send)
    await _handler(scope, receive, send)


app = App()
