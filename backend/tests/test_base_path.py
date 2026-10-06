from urllib.parse import parse_qs, urlparse

import pytest

from tests.test_mcp import HEADERS

URL = "https://docs.example.com/docs"


@pytest.fixture
def prefixed(client, configure, monkeypatch):
    monkeypatch.setenv("OHARA_URL", URL)
    return client


def test_serves_under_the_path_of_its_address(prefixed, configure):
    configure(private=False)
    assert prefixed.get("/docs/api/status").json()["configured"] is True
    assert prefixed.get("/docs/api/page", params={"path": "guide"}).json()["markdown"] == "# Guide"


def test_sends_the_rest_of_the_host_to_the_path(prefixed, configure):
    configure(private=False)
    assert prefixed.get("/").headers["location"] == "/docs/"
    assert prefixed.get("/docs").headers["location"] == "/docs/"
    assert prefixed.get("/team/onboarding?tab=1").headers["location"] == "/docs/team/onboarding?tab=1"
    assert prefixed.post("/api/github/webhook").status_code == 404


def test_github_sign_in_returns_under_the_path(prefixed, configure):
    configure(private=True)
    location = prefixed.get("/docs/api/auth/login").headers["location"]
    assert parse_qs(urlparse(location).query)["redirect_uri"] == [f"{URL}/api/auth/callback"]
    assert prefixed.post("/docs/api/auth/logout").headers["location"] == "/docs/"


def test_oauth_discovery_stays_at_the_root(prefixed, configure):
    configure(private=True)
    response = prefixed.post("/docs/mcp", json={}, headers=HEADERS)
    assert response.status_code == 401
    metadata = "https://docs.example.com/.well-known/oauth-protected-resource/docs/mcp"
    assert response.headers["WWW-Authenticate"] == f'Bearer resource_metadata="{metadata}"'
    assert prefixed.get("/.well-known/oauth-authorization-server/docs").status_code == 200
