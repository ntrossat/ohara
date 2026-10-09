import asyncio
import hashlib
import hmac
import json

import httpx
import pytest
import respx

from ohara import appconfig, appdocs, db, docs, main, store
from tests.conftest import REPO, tarball

API = "https://api.github.com"
CODE = f"{API}/repos/acme/api"


# Config


def test_repositories_without_a_config_file_are_not_synced():
    assert appconfig.parse(None) == []


def test_config_without_a_docs_list_syncs_the_docs_folder():
    assert appconfig.parse("") == ["docs"]
    assert appconfig.parse("other: 1") == ["docs"]


def test_config_lists_paths_and_drops_unsafe_ones():
    text = "docs:\n  - documentation/\n  - README.md\n  - /etc\n  - ../secrets\n  - README.md\n"
    assert appconfig.parse(text) == ["documentation", "README.md"]


def test_config_can_turn_syncing_off():
    assert appconfig.parse("docs: []") == []


@pytest.mark.parametrize("text", ["docs: [", "- docs", "docs: docs", "just text"])
def test_invalid_config_is_refused(text):
    with pytest.raises(appconfig.Invalid):
        appconfig.parse(text)


def test_layout_puts_folder_contents_and_files_at_the_root():
    files = ["docs/README.md", "docs/billing/api.md", "README.md", "src/main.py", "docs2/x.md"]
    assert appconfig.layout(["docs", "README.md"], files) == {
        "README.md": "docs/README.md",
        "billing/api.md": "docs/billing/api.md",
    }


def test_matches_synced_paths_and_the_config_file():
    assert appconfig.matches(["docs"], "docs/a.md")
    assert appconfig.matches(["docs"], ".ohara.yml")
    assert not appconfig.matches(["docs"], "docsite/a.md")
    assert not appconfig.matches([], "docs/a.md")


# Sync


def mock_sync(code_files, config="docs:\n  - docs\n", private=False):
    """Mock GitHub for a sync of acme/api. Returns the tarball route."""
    respx.post(f"{API}/app/installations/42/access_tokens").mock(return_value=httpx.Response(201, json={"token": "ghs_app"}))
    respx.get(CODE).mock(return_value=httpx.Response(200, json={"full_name": "acme/api", "name": "api", "private": private, "default_branch": "main"}))
    respx.get(f"{CODE}/contents/.ohara.yml").mock(
        return_value=httpx.Response(200, text=config) if config is not None else httpx.Response(404)
    )
    return respx.get(url__regex=rf"{CODE}/tarball/.*").mock(return_value=httpx.Response(200, content=tarball(code_files)))


def run_sync(ref=None):
    return asyncio.run(appdocs.sync(store.load(), "acme/api", ref))


def synced_files(data_dir):
    folder = data_dir / "docs" / "apps" / "api"
    return {file.relative_to(folder).as_posix(): file.read_text() for file in folder.rglob("*") if file.is_file()} if folder.exists() else {}


def add_synced_folder(data_dir):
    (data_dir / "docs" / "apps" / "api").mkdir(parents=True)
    (data_dir / "docs" / "apps" / "api" / "old.md").write_text("# Old")


@respx.mock
def test_sync_writes_the_docs_folder_with_its_source(configure, data_dir):
    configure(private=False)
    mock_sync({"docs/README.md": "# API", "docs/img/logo.png": "png", "src/app.py": "code", "docs/.hidden.md": "x"})
    run_sync("abcdef1234567890")
    assert synced_files(data_dir) == {"README.md": '---\nsource: "acme/api:docs/README.md"\n---\n\n# API', "img/logo.png": "png"}
    assert appdocs.state("acme/api") == {"name": "api", "branch": "main", "paths": ["docs"], "skipped": None}
    assert docs.search("API", 5)[0]["path"] == "apps/api"


@respx.mock
def test_sync_replaces_the_previous_copy(configure, data_dir):
    configure(private=False)
    add_synced_folder(data_dir)
    mock_sync({"docs/a.md": "# A"})
    run_sync()
    assert set(synced_files(data_dir)) == {"a.md"}


@respx.mock
def test_sync_follows_the_config_file(configure, data_dir):
    configure(private=False)
    mock_sync({"documentation/guide.md": "# Guide", "README.md": "# Readme", "docs/a.md": "# A"}, config="docs:\n  - documentation\n  - README.md\n")
    run_sync()
    assert set(synced_files(data_dir)) == {"guide.md", "README.md"}


@respx.mock
def test_sync_turned_off_removes_the_folder(configure, data_dir):
    configure(private=False)
    add_synced_folder(data_dir)
    download = mock_sync({"docs/a.md": "# A"}, config="docs: []")
    run_sync()
    assert synced_files(data_dir) == {} and not download.called


@respx.mock
def test_invalid_config_keeps_the_last_copy(configure, data_dir):
    configure(private=False)
    add_synced_folder(data_dir)
    db.put("app", "acme/api", {"name": "api", "branch": "main", "paths": ["docs"], "skipped": None})
    mock_sync({"docs/a.md": "# A"}, config="docs: [")
    run_sync()
    assert set(synced_files(data_dir)) == {"old.md"}
    record = appdocs.state("acme/api")
    assert record["paths"] == ["docs"] and "not valid YAML" in record["skipped"]


@respx.mock
def test_private_code_is_never_synced_into_a_public_docs_repository(configure, data_dir):
    configure(private=False)
    add_synced_folder(data_dir)  # a copy from when the docs repository was private
    download = mock_sync({"docs/a.md": "# A"}, private=True)
    run_sync()
    assert synced_files(data_dir) == {} and not download.called
    assert "is private" in appdocs.state("acme/api")["skipped"]


@respx.mock
def test_private_code_is_synced_into_a_private_docs_repository(configure, data_dir):
    configure(private=True)
    mock_sync({"docs/a.md": "# A"}, private=True)
    run_sync()
    assert set(synced_files(data_dir)) == {"a.md"}


@respx.mock
def test_symbolic_links_are_not_synced(configure, data_dir):
    configure(private=False)
    mock_sync({"docs/a.md": "# A"})
    respx.get(url__regex=rf"{CODE}/tarball/.*").mock(
        return_value=httpx.Response(200, content=tarball({"docs/a.md": "# A"}, links=[("docs/secret.md", "/etc/passwd")]))
    )
    run_sync()
    assert set(synced_files(data_dir)) == {"a.md"}


@respx.mock
def test_files_over_1_mb_are_not_synced(configure, data_dir):
    configure(private=False)
    mock_sync({"docs/limit.md": "x" * appdocs.MAX_SIZE, "docs/big.png": "x" * (appdocs.MAX_SIZE + 1)})
    run_sync()
    assert set(synced_files(data_dir)) == {"limit.md"}


@respx.mock
def test_at_most_500_files_are_synced(configure, data_dir):
    configure(private=False)
    mock_sync({f"docs/page-{n}.md": "# Page" for n in range(appdocs.MAX_FILES + 1)})
    run_sync()
    assert len(synced_files(data_dir)) == 500


@respx.mock
def test_a_failed_download_keeps_the_last_copy(configure, data_dir):
    configure(private=False)
    add_synced_folder(data_dir)
    mock_sync({})
    respx.get(url__regex=rf"{CODE}/tarball/.*").mock(return_value=httpx.Response(404))
    with pytest.raises(httpx.HTTPStatusError):
        run_sync("gone")
    assert set(synced_files(data_dir)) == {"old.md"}


@respx.mock
def test_sync_without_a_config_file_syncs_nothing(configure, data_dir):
    configure(private=False)
    add_synced_folder(data_dir)
    download = mock_sync({"docs/a.md": "# A"}, config=None)
    run_sync()
    assert synced_files(data_dir) == {} and not download.called
    assert appdocs.state("acme/api")["paths"] == []


@respx.mock
def test_docs_repository_is_never_synced(configure):
    configure(private=False)
    assert asyncio.run(appdocs.sync(store.load(), REPO)) is None


def test_remove_deletes_the_folder(configure, data_dir):
    configure(private=False)
    add_synced_folder(data_dir)
    db.put("app", "acme/api", {"name": "api", "branch": "main", "paths": ["docs"], "skipped": None})
    asyncio.run(appdocs.remove("acme/api"))
    assert synced_files(data_dir) == {}
    assert appdocs.state("acme/api") is None


def test_a_docs_repository_sync_keeps_the_synced_folders(data_dir):
    root = data_dir / "docs"
    add_synced_folder(data_dir)
    docs.extract(tarball({"guide.md": "# Guide", "apps/api/stale.md": "# Committed by hand"}), root)
    assert (root / "guide.md").exists()
    assert set(synced_files(data_dir)) == {"old.md"}


# Webhook


def send(client, event, payload):
    body = json.dumps(payload).encode()
    signature = "sha256=" + hmac.new(b"hook-secret", body, hashlib.sha256).hexdigest()
    headers = {"X-GitHub-Event": event, "X-Hub-Signature-256": signature, "Content-Type": "application/json"}
    return client.post("/api/github/webhook", content=body, headers=headers)


@pytest.fixture
def calls(monkeypatch):
    seen = []

    async def sync_app(full_name, ref=None):
        seen.append(("sync", full_name, ref))

    async def remove_app(full_name):
        seen.append(("remove", full_name))

    async def sync_apps():
        seen.append(("sync all",))

    async def nothing(*_):
        pass

    monkeypatch.setattr(main, "safe_sync_app", sync_app)
    monkeypatch.setattr(main, "safe_remove_app", remove_app)
    monkeypatch.setattr(main, "safe_sync_apps", sync_apps)
    monkeypatch.setattr(main, "safe_sync", nothing)
    return seen


def test_added_and_removed_repositories_are_synced(client, configure, calls):
    configure(private=False)
    payload = {"installation": {"id": 42}, "repositories_added": [{"full_name": "acme/api"}], "repositories_removed": [{"full_name": "acme/web"}]}
    assert send(client, "installation_repositories", payload).json()["apps"] is True
    assert calls == [("sync", "acme/api", None), ("remove", "acme/web")]


def test_a_change_of_docs_repository_visibility_syncs_every_app_again(client, configure, calls):
    configure(private=False)
    send(client, "repository", {"action": "publicized", "repository": {"full_name": REPO}})
    assert calls == [("sync all",)]


def push(repo, files, before="a" * 40):
    return {
        "ref": "refs/heads/main",
        "before": before,
        "after": "b" * 40,
        "repository": {"full_name": repo, "default_branch": "main"},
        "installation": {"id": 42},
        "commits": [{"added": [], "modified": files, "removed": []}],
    }


def test_push_that_changes_docs_syncs_them(configure, calls):
    configure(private=False)
    db.put("app", "acme/api", {"name": "api", "branch": "main", "paths": ["docs"], "skipped": None})
    asyncio.run(main.check_code(push("acme/api", ["docs/a.md"], before="0" * 40)))
    asyncio.run(main.check_code(push("acme/api", ["src/a.py"], before="0" * 40)))
    asyncio.run(main.check_code(push("acme/api", [".ohara.yml"], before="0" * 40)))
    assert calls == [("sync", "acme/api", "b" * 40), ("sync", "acme/api", "b" * 40)]


def test_a_push_without_a_config_file_does_not_sync(configure, calls):
    configure(private=False)
    asyncio.run(main.check_code(push("acme/web", ["docs/a.md"], before="0" * 40)))
    assert calls == []


def test_synced_pages_link_to_their_source(client, configure, data_dir):
    configure(private=False)
    db.put("app", "acme/api", {"name": "api", "branch": "trunk", "paths": ["docs"], "skipped": None})
    (data_dir / "docs" / "apps" / "api").mkdir(parents=True)
    (data_dir / "docs" / "apps" / "api" / "billing.md").write_text('---\nsource: "acme/api:docs/billing.md"\n---\n\n# Billing')
    (data_dir / "docs" / "faked.md").write_text('---\nsource: "acme/api:docs/x.md"\n---\n\n# Faked')
    page = client.get("/api/page", params={"path": "apps/api/billing"}).json()
    assert page["source"] == {"repo": "acme/api", "path": "docs/billing.md", "edit_url": "https://github.com/acme/api/edit/trunk/docs/billing.md"}
    assert client.get("/api/page", params={"path": "faked"}).json()["source"] is None


def test_sync_apps_syncs_every_repository_and_removes_orphan_folders(configure, data_dir, monkeypatch):
    configure(private=False)
    for name in ("api", "gone"):
        (data_dir / "docs" / "apps" / name).mkdir(parents=True)
    seen = []

    async def token(*_):
        return "ghs_app"

    async def repos(_):
        return [{"full_name": REPO, "name": "handbook"}, {"full_name": "acme/api", "name": "api"}, {"full_name": "acme/web", "name": "web"}]

    async def sync(_, full_name, ref=None):
        seen.append(("sync", full_name))

    async def remove(full_name):
        seen.append(("remove", full_name))

    monkeypatch.setattr(main.github, "installation_token", token)
    monkeypatch.setattr(main.github, "installation_repos", repos)
    monkeypatch.setattr(main.appdocs, "sync", sync)
    monkeypatch.setattr(main.appdocs, "remove", remove)
    asyncio.run(main.sync_apps())
    assert seen == [("sync", "acme/api"), ("sync", "acme/web"), ("remove", "acme/gone")]


def refresh_mocks(monkeypatch, docs_repo, code_repos, seen):
    async def token(*_):
        return "ghs_app"

    async def get_repo(_, full_name):
        return docs_repo

    async def repos(_):
        return code_repos

    async def record(name, *_):
        seen.append(name)

    monkeypatch.setattr(main.github, "installation_token", token)
    monkeypatch.setattr(main.github, "get_repo", get_repo)
    monkeypatch.setattr(main.github, "installation_repos", repos)
    monkeypatch.setattr(main, "safe_sync", lambda: record("docs"))
    monkeypatch.setattr(main, "safe_sync_apps", lambda: record("apps"))
    monkeypatch.setattr(main, "safe_sync_app", record)


def test_refresh_syncs_when_the_docs_repository_changed_without_a_webhook(configure, monkeypatch):
    configure(private=False)
    seen = []
    refresh_mocks(monkeypatch, {"full_name": REPO, "private": True, "default_branch": "main"}, [], seen)
    asyncio.run(main.refresh())
    assert seen == ["docs", "apps"]


def test_refresh_removes_code_repositories_made_private_from_public_docs(configure, monkeypatch):
    configure(private=False)
    db.put("app", "acme/api", {"name": "api", "branch": "main", "paths": ["docs"], "skipped": None})
    db.put("app", "acme/web", {"name": "web", "branch": "main", "paths": ["docs"], "skipped": None})
    seen = []
    code = [{"full_name": "acme/api", "name": "api", "private": True}, {"full_name": "acme/web", "name": "web", "private": False}]
    refresh_mocks(monkeypatch, {"full_name": REPO, "private": False, "default_branch": "main"}, code, seen)
    asyncio.run(main.refresh())
    assert seen == ["acme/api"]
