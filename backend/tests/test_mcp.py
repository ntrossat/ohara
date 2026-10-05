import base64
import hashlib
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from ohara import main, mcp_server, oauth, sessions
from tests.conftest import REPO

REPO_URL = f"https://api.github.com/repos/{REPO}"
HEADERS = {"Accept": "application/json, text/event-stream", "MCP-Protocol-Version": "2025-06-18"}


@pytest.fixture
def mcp(monkeypatch):
    async def no_sync():
        pass

    monkeypatch.setattr(main, "safe_sync", no_sync)
    mcp_server.checks.clear()
    with TestClient(main.app, base_url="https://docs.example.com", follow_redirects=False) as client:
        yield client


def call(client, tool, token=None, **arguments):
    headers = HEADERS | ({"Authorization": f"Bearer {token}"} if token else {})
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": tool, "arguments": arguments}}
    return client.post("/mcp", json=body, headers=headers)


def result(response):
    assert response.status_code == 200, response.text
    return response.json()["result"]


def test_public_repository_is_open_without_a_token(mcp, configure):
    configure(private=False)
    assert result(call(mcp, "read_page", path="guide"))["structuredContent"]["result"] == "# Guide"


def test_lists_pages_with_their_folders(mcp, configure, data_dir):
    configure(private=False)
    (data_dir / "docs" / "team").mkdir()
    (data_dir / "docs" / "team" / "onboarding.md").write_text("# Onboarding")
    pages = result(call(mcp, "list_pages"))["structuredContent"]["result"]
    assert {"path": "guide", "title": "Guide"} in pages
    assert {"path": "team/onboarding", "title": "Team / Onboarding"} in pages


def test_search_matches_every_word(mcp, configure, data_dir):
    configure(private=False)
    (data_dir / "docs" / "deploy.md").write_text("# Deploy\n\nShip with blue green releases.")
    found = result(call(mcp, "search", query="green DEPLOY"))["structuredContent"]["result"]
    assert found == [{"path": "deploy", "title": "Deploy", "snippet": "Ship with blue green releases."}]
    assert result(call(mcp, "search", query="red"))["structuredContent"]["result"] == []


def test_missing_page_is_a_tool_error(mcp, configure):
    configure(private=False)
    assert result(call(mcp, "read_page", path="nope"))["isError"] is True


def test_private_repository_requires_a_token(mcp, configure):
    configure(private=True)
    response = call(mcp, "list_pages")
    assert response.status_code == 401
    metadata = "https://docs.example.com/.well-known/oauth-protected-resource/mcp"
    assert response.headers["WWW-Authenticate"] == f'Bearer resource_metadata="{metadata}"'


@respx.mock
def test_token_with_repository_access_can_read(mcp, configure):
    configure(private=True)
    route = respx.get(REPO_URL).mock(return_value=httpx.Response(200, json={}))
    assert result(call(mcp, "read_page", token="ghp_1", path="guide"))["structuredContent"]["result"] == "# Guide"
    result(call(mcp, "read_page", token="ghp_1", path="guide"))
    assert route.call_count == 1  # re-checked every 5 minutes, not on each call


@respx.mock
def test_token_without_repository_access_is_rejected(mcp, configure):
    configure(private=True)
    respx.get(REPO_URL).mock(return_value=httpx.Response(404))
    assert call(mcp, "list_pages", token="ghp_1").status_code == 403


@respx.mock
def test_invalid_token_is_rejected(mcp, configure):
    configure(private=True)
    respx.get(REPO_URL).mock(return_value=httpx.Response(401))
    assert call(mcp, "list_pages", token="bad").status_code == 401


# OAuth sign-in for MCP clients

REDIRECT = "http://localhost:33418/callback"
VERIFIER = "v" * 64
CHALLENGE = base64.urlsafe_b64encode(hashlib.sha256(VERIFIER.encode()).digest()).decode().rstrip("=")


def query(url):
    return {key: values[0] for key, values in parse_qs(urlparse(url).query).items()}


def mock_github_sign_in(repo_status=200):
    respx.post("https://github.com/login/oauth/access_token").mock(
        return_value=httpx.Response(200, json={"access_token": "ghu_1", "refresh_token": "ghr_1", "expires_in": 28800})
    )
    respx.get("https://api.github.com/user").mock(return_value=httpx.Response(200, json={"login": "ada"}))
    return respx.get(REPO_URL).mock(return_value=httpx.Response(repo_status, json={}))


def authorize(client):
    """Run discovery, registration, and the browser sign-in. Returns the client id and the final redirect."""
    resource = client.get("/.well-known/oauth-protected-resource/mcp").json()
    assert resource["authorization_servers"] == ["https://docs.example.com"]
    server = client.get("/.well-known/oauth-authorization-server").json()
    registered = client.post(
        urlparse(server["registration_endpoint"]).path,
        json={"redirect_uris": [REDIRECT], "token_endpoint_auth_method": "none", "client_name": "Claude Code"},
    ).json()
    params = {
        "response_type": "code",
        "client_id": registered["client_id"],
        "redirect_uri": REDIRECT,
        "code_challenge": CHALLENGE,
        "code_challenge_method": "S256",
        "state": "client-state",
        "resource": "https://docs.example.com/mcp",
    }
    login = client.get("/authorize", params=params).headers["location"]
    github = client.get(urlparse(login).path + "?" + urlparse(login).query).headers["location"]
    done = client.get("/api/auth/callback", params={"code": "gh-code", "state": query(github)["state"]})
    assert done.status_code == 303
    return registered["client_id"], done.headers["location"]


def token(client, **form):
    return client.post("/token", data=form)


@respx.mock
def test_mcp_client_signs_in_with_github(mcp, configure):
    configure(private=True)
    mock_github_sign_in()
    client_id, redirect = authorize(mcp)
    assert redirect.startswith(REDIRECT)
    assert query(redirect)["state"] == "client-state"
    assert "ohara_session" not in mcp.cookies  # no website session from an MCP sign-in

    tokens = token(
        mcp,
        grant_type="authorization_code",
        code=query(redirect)["code"],
        redirect_uri=REDIRECT,
        client_id=client_id,
        code_verifier=VERIFIER,
        resource="https://docs.example.com/mcp",
    ).json()
    assert tokens["expires_in"] == 3600
    assert result(call(mcp, "read_page", token=tokens["access_token"], path="guide"))["structuredContent"]["result"] == "# Guide"

    refreshed = token(mcp, grant_type="refresh_token", refresh_token=tokens["refresh_token"], client_id=client_id).json()
    assert result(call(mcp, "list_pages", token=refreshed["access_token"]))
    reused = token(mcp, grant_type="refresh_token", refresh_token=tokens["refresh_token"], client_id=client_id)
    assert reused.status_code == 400  # refresh tokens rotate

    # The SDK's revocation form requires client_secret, even empty for public clients.
    mcp.post("/revoke", data={"token": refreshed["access_token"], "client_id": client_id, "client_secret": ""})
    assert call(mcp, "list_pages", token=refreshed["access_token"]).status_code == 401


@respx.mock
def test_mcp_sign_in_is_denied_without_repository_access(mcp, configure):
    configure(private=True)
    mock_github_sign_in(repo_status=404)
    _, redirect = authorize(mcp)
    assert query(redirect)["error"] == "access_denied"
    assert "code" not in query(redirect)


@respx.mock
def test_mcp_token_loses_access_with_the_repository(mcp, configure, monkeypatch):
    configure(private=True)
    repo = mock_github_sign_in()
    client_id, redirect = authorize(mcp)
    tokens = token(
        mcp, grant_type="authorization_code", code=query(redirect)["code"], redirect_uri=REDIRECT,
        client_id=client_id, code_verifier=VERIFIER,
    ).json()
    repo.mock(return_value=httpx.Response(404))
    monkeypatch.setattr(sessions, "CHECK_INTERVAL", 0)
    assert call(mcp, "list_pages", token=tokens["access_token"]).status_code == 403


def test_authorization_code_needs_the_pkce_verifier(mcp, configure):
    configure(private=True)
    with respx.mock:
        mock_github_sign_in()
        client_id, redirect = authorize(mcp)
    denied = token(
        mcp, grant_type="authorization_code", code=query(redirect)["code"], redirect_uri=REDIRECT,
        client_id=client_id, code_verifier="w" * 64,
    )
    assert denied.status_code == 400


def test_client_registrations_are_capped(mcp, configure, monkeypatch):
    configure(private=True)
    monkeypatch.setattr(oauth, "MAX_CLIENTS", 2)
    ids = [mcp.post("/register", json={"redirect_uris": [REDIRECT], "token_endpoint_auth_method": "none"}).json()["client_id"] for _ in range(3)]
    params = {"response_type": "code", "redirect_uri": REDIRECT, "code_challenge": CHALLENGE, "code_challenge_method": "S256"}
    assert mcp.get("/authorize", params=params | {"client_id": ids[0]}).status_code == 400
    assert mcp.get("/authorize", params=params | {"client_id": ids[2]}).status_code == 302
