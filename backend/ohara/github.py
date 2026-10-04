"""GitHub App calls: manifest registration, installation access, user sign-in, and webhooks."""

import hashlib
import hmac
import ipaddress
import time

import httpx
import jwt

API = "https://api.github.com"
WEB = "https://github.com"
HEADERS = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}


class Unauthorized(Exception):
    """The user token is no longer valid."""


def client(token: str | None = None) -> httpx.AsyncClient:
    headers = HEADERS | ({"Authorization": f"Bearer {token}"} if token else {})
    return httpx.AsyncClient(headers=headers, timeout=30, follow_redirects=True)


# Registration


def is_public(base_url: str) -> bool:
    """GitHub only delivers webhooks to addresses reachable over the internet."""
    host = httpx.URL(base_url).host
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")) or "." not in host:
        return False
    try:
        return ipaddress.ip_address(host).is_global
    except ValueError:
        return True


def manifest(base_url: str) -> dict:
    app = {
        "name": "Ohara docs",
        "url": base_url,
        "description": "Ohara documentation website",
        "public": False,
        "redirect_url": f"{base_url}/api/setup/callback",
        "callback_urls": [auth_callback_url(base_url)],
        "setup_url": f"{base_url}/api/setup/installed",
        "default_permissions": {"contents": "read", "metadata": "read"},
    }
    if is_public(base_url):
        # Without a webhook (local runs), docs refresh when Ohara restarts.
        app["hook_attributes"] = {"url": f"{base_url}/api/github/webhook"}
        app["default_events"] = ["push", "repository"]
    return app


def auth_callback_url(base_url: str) -> str:
    return f"{base_url}/api/auth/callback"


def install_url(app: dict) -> str:
    return f"{WEB}/apps/{app['slug']}/installations/new"


def repo_summary(repo: dict) -> dict:
    return {"full_name": repo["full_name"], "private": repo["private"], "default_branch": repo["default_branch"]}


def creation_url(org: str | None) -> str:
    if org:
        return f"{WEB}/organizations/{org}/settings/apps/new"
    return f"{WEB}/settings/apps/new"


async def convert_manifest(code: str) -> dict:
    async with client() as c:
        r = await c.post(f"{API}/app-manifests/{code}/conversions")
        r.raise_for_status()
        data = r.json()
    keys = ("id", "slug", "client_id", "client_secret", "webhook_secret", "pem")
    return {k: data[k] for k in keys}


# Installation access


def app_jwt(app: dict) -> str:
    now = int(time.time())
    return jwt.encode({"iat": now - 60, "exp": now + 540, "iss": str(app["id"])}, app["pem"], algorithm="RS256")


async def get_installation(app: dict, installation_id: int) -> dict:
    async with client(app_jwt(app)) as c:
        r = await c.get(f"{API}/app/installations/{installation_id}")
        r.raise_for_status()
        return r.json()


async def installation_token(app: dict, installation_id: int) -> str:
    async with client(app_jwt(app)) as c:
        r = await c.post(f"{API}/app/installations/{installation_id}/access_tokens")
        r.raise_for_status()
        return r.json()["token"]


async def installation_repos(token: str) -> list[dict]:
    async with client(token) as c:
        r = await c.get(f"{API}/installation/repositories", params={"per_page": 100})
        r.raise_for_status()
        return r.json()["repositories"]


async def get_repo(token: str, full_name: str) -> dict:
    async with client(token) as c:
        r = await c.get(f"{API}/repos/{full_name}")
        r.raise_for_status()
        return r.json()


async def tarball(token: str, full_name: str, ref: str) -> bytes:
    async with client(token) as c:
        r = await c.get(f"{API}/repos/{full_name}/tarball/{ref}")
        r.raise_for_status()
        return r.content


# User sign-in


def authorize_url(app: dict, redirect_uri: str, state: str) -> str:
    query = httpx.QueryParams(client_id=app["client_id"], redirect_uri=redirect_uri, state=state)
    return f"{WEB}/login/oauth/authorize?{query}"


async def _token_request(app: dict, **params) -> dict:
    async with client() as c:
        r = await c.post(
            f"{WEB}/login/oauth/access_token",
            data={"client_id": app["client_id"], "client_secret": app["client_secret"], **params},
            headers={"Accept": "application/json"},
        )
        r.raise_for_status()
        data = r.json()
    if "access_token" not in data:
        raise Unauthorized(data.get("error_description", "token request failed"))
    return data


async def exchange_code(app: dict, code: str, redirect_uri: str) -> dict:
    return await _token_request(app, code=code, redirect_uri=redirect_uri)


async def refresh_token(app: dict, refresh: str) -> dict:
    return await _token_request(app, grant_type="refresh_token", refresh_token=refresh)


async def get_user(token: str) -> dict:
    async with client(token) as c:
        r = await c.get(f"{API}/user")
        if r.status_code == 401:
            raise Unauthorized()
        r.raise_for_status()
        return r.json()


async def user_can_read(token: str, full_name: str) -> bool:
    """A user token only sees repositories both the user and the app can access."""
    async with client(token) as c:
        r = await c.get(f"{API}/repos/{full_name}")
    if r.status_code == 401:
        raise Unauthorized()
    if r.status_code in (403, 404):
        return False
    r.raise_for_status()
    return True


# Webhooks


def valid_signature(secret: str, body: bytes, header: str | None) -> bool:
    if not header:
        return False
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header)
