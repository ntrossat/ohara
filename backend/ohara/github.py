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


def app_name(base_url: str) -> str:
    """App names are unique across GitHub: use the instance's host, or a random suffix for local runs."""
    suffix = httpx.URL(base_url).host if is_public(base_url) else secrets.token_hex(3)
    return f"Ohara {suffix}"[:34]


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
        app["default_events"] = ["push", "pull_request", "repository"]
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


async def app_installations(app: dict) -> list[dict]:
    async with client(app_jwt(app)) as c:
        r = await c.get(f"{API}/app/installations")
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


# Code changes


async def changed_files(token: str, full_name: str, before: str, after: str) -> list[str]:
    """Files changed between two commits, including the old name of renamed files."""
    async with client(token) as c:
        r = await c.get(f"{API}/repos/{full_name}/compare/{before}...{after}", params={"per_page": 300})
        r.raise_for_status()
    files = set()
    for changed in r.json().get("files", []):
        files.add(changed["filename"])
        if changed.get("previous_filename"):
            files.add(changed["previous_filename"])
    return sorted(files)


# Change proposals


async def open_pull_request(token: str, full_name: str, base: str, branch: str, files: dict[str, str], title: str, body: str) -> str:
    """Commit `files` (repository path to text) on `branch` and return the URL of its pull request.

    When the branch already has an open pull request, the commits are added to it with a comment. Otherwise the
    branch starts again from `base`, so it holds only this change, and a new pull request is opened.
    """
    repo = f"{API}/repos/{full_name}"
    pull = await find_pull(token, full_name, branch)
    async with client(token) as c:
        if not pull:
            r = await c.get(f"{repo}/git/ref/heads/{quote(base)}")
            r.raise_for_status()
            sha = r.json()["object"]["sha"]
            r = await c.post(f"{repo}/git/refs", json={"ref": f"refs/heads/{branch}", "sha": sha})
            if r.status_code == 422:  # left over from an earlier, closed pull request
                r = await c.patch(f"{repo}/git/refs/heads/{quote(branch)}", json={"sha": sha, "force": True})
            r.raise_for_status()
        for path, text in files.items():
            url = f"{repo}/contents/{quote(path)}"
            current = await c.get(url, params={"ref": branch})
            content = {"message": title, "branch": branch, "content": base64.b64encode(text.encode()).decode()}
            if current.status_code == 200:
                content["sha"] = current.json()["sha"]
            r = await c.put(url, json=content)
            r.raise_for_status()
        if pull:
            r = await c.post(f"{repo}/issues/{pull['number']}/comments", json={"body": f"**{title}**\n\n{body}"})
            r.raise_for_status()
            return pull["html_url"]
        r = await c.post(f"{repo}/pulls", json={"title": title, "body": body, "head": branch, "base": base})
        r.raise_for_status()
        return r.json()["html_url"]


async def find_pull(token: str, full_name: str, branch: str) -> dict | None:
    """The open pull request of a branch, if any."""
    async with client(token) as c:
        r = await c.get(f"{API}/repos/{full_name}/pulls", params={"head": f"{full_name.split('/')[0]}:{branch}", "state": "open"})
        r.raise_for_status()
    return next(iter(r.json()), None)


async def pull_files(token: str, full_name: str, number: int) -> list[str]:
    """The files a pull request changes, including the old name of renamed files."""
    files = set()
    async with client(token) as c:
        for page in range(1, 31):  # GitHub lists up to 3,000 files
            r = await c.get(f"{API}/repos/{full_name}/pulls/{number}/files", params={"per_page": 100, "page": page})
            r.raise_for_status()
            for changed in r.json():
                files.add(changed["filename"])
                if changed.get("previous_filename"):
                    files.add(changed["previous_filename"])
            if len(r.json()) < 100:
                break
    return sorted(files)


async def merge_pull(token: str, full_name: str, number: int, sha: str) -> str | None:
    """Squash-merge a pull request at commit `sha`. Returns why GitHub refused, or None once merged."""
    async with client(token) as c:
        r = await c.put(f"{API}/repos/{full_name}/pulls/{number}/merge", json={"merge_method": "squash", "sha": sha})
    if r.status_code in (405, 409, 422):
        return r.json().get("message") or "GitHub refused the merge"
    r.raise_for_status()
    return None


async def close_pull(token: str, full_name: str, number: int) -> None:
    async with client(token) as c:
        r = await c.patch(f"{API}/repos/{full_name}/pulls/{number}", json={"state": "closed"})
        r.raise_for_status()


async def comment(token: str, full_name: str, number: int, body: str) -> None:
    async with client(token) as c:
        r = await c.post(f"{API}/repos/{full_name}/issues/{number}/comments", json={"body": body})
        r.raise_for_status()


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


async def user_can_write(token: str, full_name: str, login: str) -> bool:
    async with client(token) as c:
        r = await c.get(f"{API}/repos/{full_name}")
        if r.status_code == 401:
            raise Unauthorized()
        if not r.is_success:
            return False
        if "permissions" in r.json():
            return bool(r.json()["permissions"].get("push"))
        r = await c.get(f"{API}/repos/{full_name}/collaborators/{quote(login)}/permission")
    return r.is_success and r.json().get("permission") in ("admin", "maintain", "write")


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
