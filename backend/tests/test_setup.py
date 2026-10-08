import json
import time
from urllib.parse import parse_qs, urlparse

import httpx
import respx

from ohara import db, github, store
from tests.conftest import REPO, tarball


def start_setup(client, org=""):
    """Return the manifest response and the setup state GitHub sends back."""
    body = client.get("/api/setup/manifest", params={"org": org}).json()
    return body, parse_qs(urlparse(body["action"]).query)["state"][0]


def test_manifest_points_github_back_to_this_instance(client):
    body, state = start_setup(client, "acme")
    assert body["action"] == f"https://github.com/organizations/acme/settings/apps/new?state={state}"
    manifest = json.loads(body["manifest"])
    assert manifest["redirect_url"] == "https://docs.example.com/api/setup/callback"
    assert manifest["callback_urls"] == ["https://docs.example.com/api/auth/callback"]
    assert manifest["hook_attributes"]["url"] == "https://docs.example.com/api/github/webhook"
    assert manifest["default_permissions"] == {"contents": "write", "pull_requests": "write", "metadata": "read"}
    assert manifest["public"] is False
    assert manifest["setup_on_update"] is True
    assert manifest["name"] == "Ohara docs.example.com"


def test_local_app_names_differ():
    from ohara import github

    assert github.app_name("http://localhost:8000") != github.app_name("http://localhost:8000")


@respx.mock
def test_callback_saves_app_and_sends_admin_to_install(client, app_credentials):
    _, state = start_setup(client)
    respx.post("https://api.github.com/app-manifests/abc/conversions").mock(
        return_value=httpx.Response(201, json=app_credentials | {"name": "Ohara docs"})
    )
    response = client.get("/api/setup/callback", params={"code": "abc", "state": state})
    assert response.headers["location"] == "https://github.com/apps/ohara-docs/installations/new"
    assert store.load()["app"] == app_credentials
    assert (db.path().stat().st_mode & 0o777) == 0o600
    assert client.get("/api/setup/callback", params={"code": "abc", "state": state}).status_code == 400  # each state works once


def test_callback_rejects_forged_state(client):
    client.get("/api/setup/manifest")
    assert client.get("/api/setup/callback", params={"code": "abc", "state": "forged"}).status_code == 400


def test_callback_rejects_expired_state(client, monkeypatch):
    _, state = start_setup(client)
    later = time.time() + 601
    monkeypatch.setattr(time, "time", lambda: later)
    response = client.get("/api/setup/callback", params={"code": "abc", "state": state})
    assert response.status_code == 400
    assert "start setup again" in response.json()["detail"]


INSTALLATION = {"id": 42, "account": {"login": "acme"}, "html_url": "https://github.com/organizations/acme/settings/installations/42"}


def mock_installation(repos):
    respx.get("https://api.github.com/app/installations/42").mock(return_value=httpx.Response(200, json=INSTALLATION))
    respx.post("https://api.github.com/app/installations/42/access_tokens").mock(
        return_value=httpx.Response(201, json={"token": "ghs_1"})
    )
    respx.get("https://api.github.com/installation/repositories").mock(
        return_value=httpx.Response(200, json={"repositories": repos})
    )


@respx.mock
def test_install_selects_the_repository_and_syncs(client, app_credentials, data_dir):
    store.save({"app": app_credentials})
    repo = {"full_name": REPO, "name": "handbook", "private": True, "default_branch": "trunk"}
    mock_installation([repo])
    respx.get(f"https://api.github.com/repos/{REPO}").mock(return_value=httpx.Response(200, json=repo))
    respx.get(f"https://api.github.com/repos/{REPO}/tarball/trunk").mock(
        return_value=httpx.Response(200, content=tarball({"README.md": "# Welcome"}))
    )
    response = client.get("/api/setup/installed", params={"installation_id": 42})
    assert response.headers["location"] == "/"
    assert store.load()["repo"] == github.repo_summary(repo)
    assert (data_dir / "docs/README.md").read_text() == "# Welcome"


@respx.mock
def test_install_on_several_repositories_asks_for_the_docs_repository(client, app_credentials, data_dir):
    store.save({"app": app_credentials})
    docs = {"full_name": REPO, "name": "handbook", "private": True, "default_branch": "trunk"}
    mock_installation([{"full_name": "acme/web", "name": "web", "private": False, "default_branch": "main"}, docs])
    response = client.get("/api/setup/installed", params={"installation_id": 42})
    assert response.headers["location"] == "/setup"
    assert store.load()["installation_id"] == 42
    assert not store.configured()
    assert client.get("/api/status").json()["installed"] is True

    assert client.get("/api/setup/repositories").json() == [
        {"full_name": REPO, "private": True},
        {"full_name": "acme/web", "private": False},
    ]
    assert client.post("/api/setup/repository", json={"full_name": "other/repo"}).status_code == 400
    respx.get(f"https://api.github.com/repos/{REPO}").mock(return_value=httpx.Response(200, json=docs))
    respx.get(f"https://api.github.com/repos/{REPO}/tarball/trunk").mock(
        return_value=httpx.Response(200, content=tarball({"README.md": "# Welcome"}))
    )
    assert client.post("/api/setup/repository", json={"full_name": REPO}).json() == {"repo": REPO}
    assert store.load()["repo"] == github.repo_summary(docs)
    assert (data_dir / "docs/README.md").read_text() == "# Welcome"


def test_choosing_needs_an_installation(client, app_credentials):
    store.save({"app": app_credentials})
    assert client.get("/api/setup/repositories").status_code == 400
    assert client.post("/api/setup/repository", json={"full_name": REPO}).status_code == 400


@respx.mock
def test_check_again_finds_the_installation(client, app_credentials):
    store.save({"app": app_credentials})
    respx.get("https://api.github.com/app/installations").mock(return_value=httpx.Response(200, json=[{"id": 42}]))
    mock_installation([{"full_name": f"a/{n}", "name": n, "private": True, "default_branch": "main"} for n in "12"])
    response = client.get("/api/setup/installed")
    assert response.headers["location"] == "/setup"
    assert store.load()["installation_id"] == 42


@respx.mock
def test_check_again_without_installation_returns_to_setup(client, app_credentials):
    store.save({"app": app_credentials})
    respx.get("https://api.github.com/app/installations").mock(return_value=httpx.Response(200, json=[]))
    assert client.get("/api/setup/installed").headers["location"] == "/setup"


def test_setup_is_locked_once_configured(client, configure):
    configure()
    assert client.get("/api/setup/manifest").status_code == 409
    assert client.get("/api/setup/callback", params={"code": "x", "state": "y"}).status_code == 409
    assert client.get("/api/setup/installed", params={"installation_id": 1}).headers["location"] == "/"  # back from adding a repository
    assert client.get("/api/setup/repositories").status_code == 409
    assert client.post("/api/setup/repository", json={"full_name": REPO}).status_code == 409


def test_status_guides_setup(client, app_credentials):
    assert client.get("/api/status").json() == {
        "configured": False,
        "url": "https://docs.example.com",
        "install_url": None,
        "installed": False,
    }
    store.save({"app": app_credentials})
    assert client.get("/api/status").json()["install_url"] == "https://github.com/apps/ohara-docs/installations/new"


def test_local_instances_get_no_webhook():
    from ohara import github

    assert "hook_attributes" not in github.manifest("http://localhost:8000")
    assert "default_events" not in github.manifest("http://127.0.0.1:8000")
    assert "hook_attributes" not in github.manifest("http://192.168.1.20:8000")
    assert "hook_attributes" not in github.manifest("http://ohara:8000")
    assert github.manifest("https://docs.example.com")["default_events"] == ["push", "repository"]
