import pytest

from ohara import store

TOKEN = "s3cret-token"
LOCKED = "Setup is locked: open the setup link that came with this instance"


@pytest.fixture
def token(monkeypatch):
    monkeypatch.setenv("OHARA_SETUP_TOKEN", TOKEN)


def test_setup_open_without_token_env(client):
    assert client.get("/api/setup/manifest").status_code == 200
    assert client.get("/api/status").json()["locked"] is False


def test_setup_refused_without_cookie(client, token, app_credentials):
    response = client.get("/api/setup/manifest")
    assert response.status_code == 403
    assert response.json()["detail"] == LOCKED
    assert client.get("/api/setup/callback", params={"code": "x", "state": "y"}).status_code == 403
    assert client.get("/api/setup/repositories").status_code == 403
    assert client.post("/api/setup/repository", json={"full_name": "a/b"}).status_code == 403
    store.save({"app": app_credentials})
    assert client.get("/api/setup/installed", params={"installation_id": 42}).status_code == 403
    assert client.get("/api/status").json()["locked"] is True


def test_start_sets_cookie_and_redirects(client, token):
    response = client.get("/api/setup/start", params={"token": TOKEN})
    assert response.status_code == 303
    assert response.headers["location"] == "/setup"
    cookie = response.headers["set-cookie"]
    assert "ohara_setup=" in cookie and "HttpOnly" in cookie


def test_start_wrong_token(client, token):
    response = client.get("/api/setup/start", params={"token": "wrong"})
    assert response.status_code == 403
    assert response.json()["detail"] == LOCKED


def test_setup_allowed_with_cookie(client, token):
    client.get("/api/setup/start", params={"token": TOKEN})
    assert client.get("/api/setup/manifest").status_code == 200
    assert client.get("/api/status").json()["locked"] is False


def test_installed_still_returns_home_once_configured(client, token, configure):
    configure()
    assert client.get("/api/setup/installed", params={"installation_id": 1}).headers["location"] == "/"
