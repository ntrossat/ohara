import json

import httpx
import respx

from ohara import sessions, store
from tests.conftest import REPO, tarball


def test_manifest_points_github_back_to_this_instance(client):
    body = client.get("/api/setup/manifest", params={"org": "acme"}).json()
    state = store.load()["setup_state"]
    assert body["action"] == f"https://github.com/organizations/acme/settings/apps/new?state={state}"
    manifest = json.loads(body["manifest"])
    assert manifest["redirect_url"] == "https://docs.example.com/api/setup/callback"
    assert manifest["callback_urls"] == ["https://docs.example.com/api/auth/callback"]
    assert manifest["hook_attributes"]["url"] == "https://docs.example.com/api/github/webhook"
    assert manifest["default_permissions"] == {"contents": "write", "pull_requests": "write", "metadata": "read"}
    assert manifest["public"] is False
    assert manifest["name"] == "Ohara docs.example.com"


def test_local_app_names_differ():
    from ohara import github

    assert github.app_name("http://localhost:8000") != github.app_name("http://localhost:8000")


@respx.mock
def test_callback_saves_app_and_sends_admin_to_install(client, app_credentials):
    client.get("/api/setup/manifest")
    state = store.load()["setup_state"]
    respx.post("https://api.github.com/app-manifests/abc/conversions").mock(
        return_value=httpx.Response(201, json=app_credentials | {"name": "Ohara docs"})
    )
    response = client.get("/api/setup/callback", params={"code": "abc", "state": state})
    assert response.headers["location"] == "https://github.com/apps/ohara-docs/installations/new"
    assert store.load()["app"] == app_credentials
    assert (store.path().stat().st_mode & 0o777) == 0o600


def test_callback_rejects_forged_state(client):
    client.get("/api/setup/manifest")
    assert client.get("/api/setup/callback", params={"code": "abc", "state": "forged"}).status_code == 400


def mock_installation(repos):
    respx.get("https://api.github.com/app/installations/42").mock(return_value=httpx.Response(200, json={"id": 42}))
    respx.post("https://api.github.com/app/installations/42/access_tokens").mock(
        return_value=httpx.Response(201, json={"token": "ghs_1"})
    )
    respx.get("https://api.github.com/installation/repositories").mock(
        return_value=httpx.Response(200, json={"repositories": repos})
    )


@respx.mock
def test_install_selects_the_repository_and_syncs(client, app_credentials, data_dir):
    store.save({"app": app_credentials})
    repo = {"full_name": REPO, "private": True, "default_branch": "trunk"}
    mock_installation([repo])
    respx.get(f"https://api.github.com/repos/{REPO}").mock(return_value=httpx.Response(200, json=repo))
    respx.get(f"https://api.github.com/repos/{REPO}/tarball/trunk").mock(
        return_value=httpx.Response(200, content=tarball({"README.md": "# Welcome"}))
    )
    response = client.get("/api/setup/installed", params={"installation_id": 42})
    assert response.headers["location"] == "/"
    assert store.load()["repo"] == repo
    assert (data_dir / "docs/README.md").read_text() == "# Welcome"


@respx.mock
def test_install_on_several_repositories_is_refused(client, app_credentials):
    store.save({"app": app_credentials})
    mock_installation([{"full_name": "a/1"}, {"full_name": "a/2"}])
    response = client.get("/api/setup/installed", params={"installation_id": 42})
    assert response.headers["location"] == "/setup?error=one-repository"
    assert not store.configured()


def test_setup_is_locked_once_configured(client, configure):
    configure()
    assert client.get("/api/setup/manifest").status_code == 409
    assert client.get("/api/setup/callback", params={"code": "x", "state": "y"}).status_code == 409
    assert client.get("/api/setup/installed", params={"installation_id": 1}).status_code == 409


def test_status_guides_setup(client, app_credentials):
    assert client.get("/api/status").json() == {"configured": False, "url": "https://docs.example.com", "install_url": None}
    store.save({"app": app_credentials})
    assert client.get("/api/status").json()["install_url"] == "https://github.com/apps/ohara-docs/installations/new"


def test_local_instances_get_no_webhook():
    from ohara import github

    assert "hook_attributes" not in github.manifest("http://localhost:8000")
    assert "default_events" not in github.manifest("http://127.0.0.1:8000")
    assert "hook_attributes" not in github.manifest("http://192.168.1.20:8000")
    assert "hook_attributes" not in github.manifest("http://ohara:8000")
    assert github.manifest("https://docs.example.com")["default_events"] == ["push", "pull_request", "repository"]


def test_settings_from_json_files_are_imported(client, data_dir, app_credentials):
    repo = {"full_name": "acme/handbook", "private": True, "default_branch": "main"}
    (data_dir / "settings.json").write_text(json.dumps({"app": app_credentials, "installation_id": 42, "repo": repo}))
    (data_dir / "sessions.json").write_text(json.dumps({"sid-1": {"login": "ada", "avatar": "", "token": "ghu_1", "refresh": None, "expires_at": None}}))
    assert store.load()["repo"] == repo
    assert sessions.get("sid-1").login == "ada"
    assert not (data_dir / "settings.json").exists()
    assert (data_dir / "settings.json.imported").exists()
