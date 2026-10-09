"""GitHub App calls: manifest registration, installation access, change proposals, user sign-in, and webhooks."""

import base64
import hashlib
import hmac
import ipaddress
import secrets
import time
from urllib.parse import quote

import httpx
import jwt

API = "https://api.github.com"
WEB = "https://github.com"
HEADERS = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
TIMEOUT = 30  # seconds per request
JWT_TTL = 540  # seconds, under GitHub's 10-minute limit
CLOCK_SKEW = 60  # seconds the app JWT is backdated, in case GitHub's clock is behind
PAGE_SIZE = 100  # GitHub's largest page

_client: httpx.AsyncClient | None = None


class Unauthorized(Exception):
    """The user token is no longer valid."""


def client() -> httpx.AsyncClient:
    """The one client for every GitHub call, created on first use, and again after `close`."""
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(headers=HEADERS, timeout=TIMEOUT, follow_redirects=True)
    return _client


async def close() -> None:
    if _client is not None:
        await _client.aclose()


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


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


def app_name(base_url: str) -> str:
    """App names are unique across GitHub: use the instance's host, with a random suffix for local runs."""
    host = httpx.URL(base_url).host
    suffix = host if is_public(base_url) else f"{host}#{secrets.token_hex(3)}"
    return f"Ohara // {suffix}"[:34]


def manifest(base_url: str) -> dict:
    app = {
        "name": app_name(base_url),
        "url": base_url,
        "description": "Ohara documentation website",
        "public": False,
        "redirect_url": f"{base_url}/api/setup/callback",
        "callback_urls": [auth_callback_url(base_url)],
        "setup_url": f"{base_url}/api/setup/installed",
        "setup_on_update": True,  # GitHub sends the admin back after changing the repository selection
        "default_permissions": {"contents": "write", "pull_requests": "write", "metadata": "read"},
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


def repo_fields(repo: dict) -> dict:
    """What callers use of a repository: its summary and its name."""
    return repo_summary(repo) | {"name": repo["name"]}


def creation_url(org: str | None) -> str:
    if org:
        return f"{WEB}/organizations/{org}/settings/apps/new"
    return f"{WEB}/settings/apps/new"


async def convert_manifest(code: str) -> dict:
    r = await client().post(f"{API}/app-manifests/{code}/conversions")
    r.raise_for_status()
    data = r.json()
    keys = ("id", "slug", "client_id", "client_secret", "webhook_secret", "pem")
    return {k: data[k] for k in keys}


# Installation access


def app_jwt(app: dict) -> str:
    now = int(time.time())
    return jwt.encode({"iat": now - CLOCK_SKEW, "exp": now + JWT_TTL, "iss": str(app["id"])}, app["pem"], algorithm="RS256")


async def get_installation(app: dict, installation_id: int) -> dict:
    """The installation's account login and its settings page."""
    r = await client().get(f"{API}/app/installations/{installation_id}", headers=auth(app_jwt(app)))
    r.raise_for_status()
    data = r.json()
    return {"id": data["id"], "account": data["account"]["login"], "html_url": data["html_url"]}


async def app_installations(app: dict) -> list[dict]:
    r = await client().get(f"{API}/app/installations", headers=auth(app_jwt(app)))
    r.raise_for_status()
    return [{"id": installation["id"]} for installation in r.json()]


async def installation_token(app: dict, installation_id: int) -> str:
    r = await client().post(f"{API}/app/installations/{installation_id}/access_tokens", headers=auth(app_jwt(app)))
    r.raise_for_status()
    return r.json()["token"]


async def installation_repos(token: str) -> list[dict]:
    repos, page = [], 1
    while True:
        r = await client().get(f"{API}/installation/repositories", params={"per_page": PAGE_SIZE, "page": page}, headers=auth(token))
        r.raise_for_status()
        batch = r.json()["repositories"]
        repos += [repo_fields(repo) for repo in batch]
        if len(batch) < PAGE_SIZE:
            return repos
        page += 1


async def get_repo(token: str, full_name: str) -> dict:
    r = await client().get(f"{API}/repos/{full_name}", headers=auth(token))
    r.raise_for_status()
    return repo_fields(r.json())


async def tarball(token: str, full_name: str, ref: str) -> bytes:
    r = await client().get(f"{API}/repos/{full_name}/tarball/{ref}", headers=auth(token))
    r.raise_for_status()
    return r.content


# Code changes


async def changed_files(token: str, full_name: str, before: str, after: str) -> list[str]:
    """Files changed between two commits, including the old name of renamed files."""
    r = await client().get(f"{API}/repos/{full_name}/compare/{before}...{after}", params={"per_page": 300}, headers=auth(token))
    r.raise_for_status()
    files = set()
    for changed in r.json().get("files", []):
        files.add(changed["filename"])
        if changed.get("previous_filename"):
            files.add(changed["previous_filename"])
    return sorted(files)


# App docs sync


async def get_file(token: str, full_name: str, path: str, ref: str) -> str | None:
    """A file's text at `ref`, or None when it doesn't exist."""
    r = await client().get(
        f"{API}/repos/{full_name}/contents/{quote(path)}",
        params={"ref": ref},
        headers=auth(token) | {"Accept": "application/vnd.github.raw"},
    )
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.text


# Change proposals


async def open_pull_request(token: str, full_name: str, base: str, branch: str, files: dict[str, str], title: str, body: str) -> str:
    """Commit `files` (repository path to text) on `branch` and return the URL of its pull request.

    When the branch already has an open pull request, the commits are added to it with a comment. Otherwise the
    branch starts again from `base`, so it holds only this change, and a new pull request is opened.
    """
    repo, c, headers = f"{API}/repos/{full_name}", client(), auth(token)
    pull = await find_pull(token, full_name, branch)
    if not pull:
        r = await c.get(f"{repo}/git/ref/heads/{quote(base)}", headers=headers)
        r.raise_for_status()
        sha = r.json()["object"]["sha"]
        r = await c.post(f"{repo}/git/refs", json={"ref": f"refs/heads/{branch}", "sha": sha}, headers=headers)
        if r.status_code == 422:  # left over from an earlier, closed pull request
            r = await c.patch(f"{repo}/git/refs/heads/{quote(branch)}", json={"sha": sha, "force": True}, headers=headers)
        r.raise_for_status()
    for path, text in files.items():
        url = f"{repo}/contents/{quote(path)}"
        current = await c.get(url, params={"ref": branch}, headers=headers)
        content = {"message": title, "branch": branch, "content": base64.b64encode(text.encode()).decode()}
        if current.status_code == 200:
            content["sha"] = current.json()["sha"]
        r = await c.put(url, json=content, headers=headers)
        r.raise_for_status()
    if pull:
        r = await c.post(f"{repo}/issues/{pull['number']}/comments", json={"body": f"**{title}**\n\n{body}"}, headers=headers)
        r.raise_for_status()
        return pull["html_url"]
    r = await c.post(f"{repo}/pulls", json={"title": title, "body": body, "head": branch, "base": base}, headers=headers)
    r.raise_for_status()
    return r.json()["html_url"]


async def pull_branch(token: str, full_name: str, number: int) -> str | None:
    """The branch of an open pull request of the repository, or None when it is closed or comes from a fork."""
    r = await client().get(f"{API}/repos/{full_name}/pulls/{number}", headers=auth(token))
    if r.status_code == 404:
        return None
    r.raise_for_status()
    pull = r.json()
    same_repo = (pull["head"].get("repo") or {}).get("full_name") == full_name
    return pull["head"]["ref"] if pull["state"] == "open" and same_repo else None


async def find_pull(token: str, full_name: str, branch: str) -> dict | None:
    """The number and URL of the open pull request of a branch, if any."""
    params = {"head": f"{full_name.split('/')[0]}:{branch}", "state": "open"}
    r = await client().get(f"{API}/repos/{full_name}/pulls", params=params, headers=auth(token))
    r.raise_for_status()
    pull = next(iter(r.json()), None)
    return {"number": pull["number"], "html_url": pull["html_url"]} if pull else None


# User sign-in


def authorize_url(app: dict, redirect_uri: str, state: str) -> str:
    query = httpx.QueryParams(client_id=app["client_id"], redirect_uri=redirect_uri, state=state)
    return f"{WEB}/login/oauth/authorize?{query}"


async def _token_request(app: dict, **params: str) -> dict:
    r = await client().post(
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
    """The user's login and avatar."""
    r = await client().get(f"{API}/user", headers=auth(token))
    if r.status_code == 401:
        raise Unauthorized()
    r.raise_for_status()
    data = r.json()
    return {"login": data["login"], "avatar_url": data.get("avatar_url", "")}


async def user_can_write(token: str, full_name: str) -> bool:
    r = await client().get(f"{API}/repos/{full_name}", headers=auth(token))
    if r.status_code == 401:
        raise Unauthorized()
    return r.is_success and bool(r.json().get("permissions", {}).get("push"))


async def user_can_read(token: str, full_name: str) -> bool:
    """A user token only sees repositories both the user and the app can access."""
    r = await client().get(f"{API}/repos/{full_name}", headers=auth(token))
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
