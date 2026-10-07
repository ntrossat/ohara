import asyncio
import base64
import hashlib
import hmac
import json

import httpx
import pytest
import respx

from ohara import appconfig, appdocs, db, docs, store
from tests.conftest import REPO

API = "https://api.github.com"
DOCS = f"{API}/repos/{REPO}"
CODE = f"{API}/repos/acme/api"


# Config


def test_config_defaults_to_the_docs_folder():
    assert appconfig.parse(None) == ["docs"]
    assert appconfig.parse("") == ["docs"]


def test_config_lists_paths_and_drops_unsafe_ones():
    text = "docs:\n  - documentation/\n  - README.md\n  - /etc\n  - ../secrets\n  - README.md\n"
    assert appconfig.parse(text) == ["documentation", "README.md"]


def test_config_can_turn_syncing_off():
    assert appconfig.parse("docs: []") == []


@pytest.mark.parametrize("text", ["docs: [", "- docs", "docs: docs"])
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


def blob(text):
    return {"content": base64.b64encode(text.encode()).decode()}


def mock_sync(code_files, docs_files=None, config=None, private=False, protected=False):
    """Mock GitHub for a sync of acme/api. Returns the routes that write to the docs repository."""
    respx.post(f"{API}/app/installations/42/access_tokens").mock(return_value=httpx.Response(201, json={"token": "ghs_app"}))
    respx.get(CODE).mock(return_value=httpx.Response(200, json={"name": "api", "private": private, "default_branch": "main"}))
    respx.get(f"{CODE}/contents/.ohara.yml").mock(
        return_value=httpx.Response(200, text=config) if config is not None else httpx.Response(404)
    )
    tree = [{"path": path, "type": "blob", "mode": "100644", "sha": f"sha-{path}", "size": len(text)} for path, text in code_files.items()]
    respx.get(url__regex=rf"{CODE}/git/trees/.*").mock(return_value=httpx.Response(200, json={"tree": tree}))
    for path, text in code_files.items():
        respx.get(f"{CODE}/git/blobs/sha-{path}").mock(return_value=httpx.Response(200, json=blob(text)))
    current = [{"path": path, "type": "blob", "sha": sha} for path, sha in (docs_files or {}).items()]
    respx.get(f"{DOCS}/git/trees/main").mock(return_value=httpx.Response(200, json={"tree": current}))
    blobs = respx.post(f"{DOCS}/git/blobs").mock(return_value=httpx.Response(201, json={"sha": "new-blob"}))
    respx.get(f"{DOCS}/git/ref/heads/main").mock(return_value=httpx.Response(200, json={"object": {"sha": "head"}}))
    respx.get(f"{DOCS}/git/commits/head").mock(return_value=httpx.Response(200, json={"tree": {"sha": "head-tree"}}))
    trees = respx.post(f"{DOCS}/git/trees").mock(return_value=httpx.Response(201, json={"sha": "tree"}))
    commits = respx.post(f"{DOCS}/git/commits").mock(return_value=httpx.Response(201, json={"sha": "commit"}))
    move = respx.patch(f"{DOCS}/git/refs/heads/main").mock(
        return_value=httpx.Response(422, json={"message": "Protected branch"}) if protected else httpx.Response(200, json={})
    )
    return {"blobs": blobs, "trees": trees, "commits": commits, "move": move}


def run_sync(ref=None):
    return asyncio.run(appdocs.sync(store.load(), "acme/api", ref))


def written(routes):
    return {entry["path"]: entry["sha"] for entry in json.loads(routes["trees"].calls.last.request.content)["tree"]}


@respx.mock
def test_sync_commits_the_docs_folder_with_its_source(configure):
    configure(private=False)
    routes = mock_sync({"docs/README.md": "# API", "docs/img/logo.png": "png", "src/app.py": "code", "docs/.hidden.md": "x"})
    assert run_sync("abcdef1234567890") is None
    assert written(routes) == {"apps/api/README.md": "new-blob", "apps/api/img/logo.png": "new-blob"}
    first = json.loads(routes["blobs"].calls[0].request.content)
    assert base64.b64decode(first["content"]).decode() == '---\nsource: "acme/api:docs/README.md"\n---\n\n# API'
    commit = json.loads(routes["commits"].calls.last.request.content)
    assert commit == {"message": "docs: sync acme/api@abcdef123456", "tree": "tree", "parents": ["head"]}
    assert routes["move"].called
    assert appdocs.state("acme/api") == {"name": "api", "branch": "main", "paths": ["docs"], "skipped": None}


@respx.mock
def test_sync_removes_deleted_files_and_skips_unchanged_ones(configure):
    configure(private=False)
    synced = '---\nsource: "acme/api:docs/a.md"\n---\n\n# A'
    unchanged = appdocs.git_sha(synced.encode())
    routes = mock_sync({"docs/a.md": "# A"}, {"apps/api/a.md": unchanged, "apps/api/old.md": "old", "apps/other/x.md": "x"})
    run_sync()
    assert written(routes) == {"apps/api/old.md": None}
    assert not routes["blobs"].called


@respx.mock
def test_sync_without_changes_makes_no_commit(configure):
    configure(private=False)
    synced = '---\nsource: "acme/api:docs/a.md"\n---\n\n# A'
    routes = mock_sync({"docs/a.md": "# A"}, {"apps/api/a.md": appdocs.git_sha(synced.encode())})
    run_sync()
    assert not routes["trees"].called


@respx.mock
def test_sync_follows_the_config_file(configure):
    configure(private=False)
    routes = mock_sync({"documentation/guide.md": "# Guide", "README.md": "# Readme", "docs/a.md": "# A"}, config="docs:\n  - documentation\n  - README.md\n")
    run_sync()
    assert set(written(routes)) == {"apps/api/guide.md", "apps/api/README.md"}


@respx.mock
def test_sync_turned_off_removes_the_folder(configure):
    configure(private=False)
    routes = mock_sync({"docs/a.md": "# A"}, {"apps/api/a.md": "sha"}, config="docs: []")
    run_sync()
    assert written(routes) == {"apps/api/a.md": None}


@respx.mock
def test_invalid_config_keeps_the_last_copy(configure):
    configure(private=False)
    db.put("app", "acme/api", {"name": "api", "branch": "main", "paths": ["docs"], "skipped": None})
    routes = mock_sync({"docs/a.md": "# A"}, config="docs: [")
    run_sync()
    assert not routes["trees"].called
    record = appdocs.state("acme/api")
    assert record["paths"] == ["docs"] and "not valid YAML" in record["skipped"]


@respx.mock
def test_private_code_is_never_synced_into_a_public_docs_repository(configure):
    configure(private=False)
    routes = mock_sync({"docs/a.md": "# A"}, private=True)
    run_sync()
    assert not routes["trees"].called
    assert "is private" in appdocs.state("acme/api")["skipped"]


@respx.mock
def test_private_code_leaves_a_docs_repository_made_public(configure):
    configure(private=False)
    routes = mock_sync({"docs/a.md": "# A"}, {"apps/api/a.md": "sha"}, private=True)
    run_sync()
    assert written(routes) == {"apps/api/a.md": None}


@respx.mock
def test_symbolic_links_are_not_synced(configure):
    configure(private=False)
    routes = mock_sync({"docs/a.md": "# A"})
    link = {"path": "docs/secret.md", "type": "blob", "mode": "120000", "sha": "link", "size": 10}
    respx.get(url__regex=rf"{CODE}/git/trees/.*").mock(
        return_value=httpx.Response(200, json={"tree": [link, {"path": "docs/a.md", "type": "blob", "mode": "100644", "sha": "sha-docs/a.md", "size": 3}]})
    )
    run_sync()
    assert written(routes) == {"apps/api/a.md": "new-blob"}


def test_docs_repository_made_public_syncs_every_app_again(client, configure, calls):
    configure(private=False)
    db.put("app", "acme/api", {"name": "api", "branch": "main", "paths": [], "skipped": "private"})
    send(client, "repository", {"action": "publicized", "repository": {"full_name": REPO}})
    assert calls == [("sync", "acme/api", None)]


@respx.mock
def test_private_code_is_synced_into_a_private_docs_repository(configure):
    configure(private=True)
    routes = mock_sync({"docs/a.md": "# A"}, private=True)
    run_sync()
    assert written(routes) == {"apps/api/a.md": "new-blob"}


@respx.mock
def test_protected_branch_gets_a_pull_request(configure):
    configure(private=False)
    mock_sync({"docs/a.md": "# A"}, protected=True)
    respx.post(f"{DOCS}/git/refs").mock(return_value=httpx.Response(201, json={}))
    branch = respx.patch(f"{DOCS}/git/refs/heads/ohara/sync-api").mock(return_value=httpx.Response(200, json={}))
    respx.get(f"{DOCS}/git/ref/heads/ohara/sync-api").mock(return_value=httpx.Response(200, json={"object": {"sha": "head"}}))
    respx.get(f"{DOCS}/pulls").mock(return_value=httpx.Response(200, json=[]))
    pull = respx.post(f"{DOCS}/pulls").mock(return_value=httpx.Response(201, json={"html_url": "https://github.com/acme/handbook/pull/9"}))
    assert run_sync() == "https://github.com/acme/handbook/pull/9"
    assert branch.called and json.loads(pull.calls.last.request.content)["head"] == "ohara/sync-api"


@respx.mock
def test_docs_repository_is_never_synced(configure):
    configure(private=False)
    assert asyncio.run(appdocs.sync(store.load(), REPO)) is None


@respx.mock
def test_remove_deletes_the_folder(configure):
    configure(private=False)
    db.put("app", "acme/api", {"name": "api", "branch": "main", "paths": ["docs"], "skipped": None})
    routes = mock_sync({}, {"apps/api/a.md": "sha", "guide.md": "g"})
    asyncio.run(appdocs.remove(store.load(), "acme/api"))
    assert written(routes) == {"apps/api/a.md": None}
    assert appdocs.state("acme/api") is None


# Webhook


def send(client, event, payload):
    body = json.dumps(payload).encode()
    signature = "sha256=" + hmac.new(b"hook-secret", body, hashlib.sha256).hexdigest()
    headers = {"X-GitHub-Event": event, "X-Hub-Signature-256": signature, "Content-Type": "application/json"}
    return client.post("/api/github/webhook", content=body, headers=headers)


@pytest.fixture
def calls(monkeypatch):
    from ohara import main

    seen = []

    async def sync_app(full_name, ref=None):
        seen.append(("sync", full_name, ref))

    async def remove_app(full_name):
        seen.append(("remove", full_name))

    async def nothing(*_):
        pass

    monkeypatch.setattr(main, "safe_sync_app", sync_app)
    monkeypatch.setattr(main, "safe_remove_app", remove_app)
    monkeypatch.setattr(main, "safe_sync", nothing)
    return seen


def test_added_and_removed_repositories_are_synced(client, configure, calls):
    configure(private=False)
    payload = {"installation": {"id": 42}, "repositories_added": [{"full_name": "acme/api"}], "repositories_removed": [{"full_name": "acme/web"}]}
    assert send(client, "installation_repositories", payload).json()["apps"] is True
    assert calls == [("sync", "acme/api", None), ("remove", "acme/web")]


def push(repo, files, sender="ada", before="a" * 40):
    return {
        "ref": "refs/heads/main",
        "before": before,
        "after": "b" * 40,
        "repository": {"full_name": repo, "default_branch": "main"},
        "installation": {"id": 42},
        "sender": {"login": sender},
        "commits": [{"added": [], "modified": files, "removed": []}],
    }


def test_push_that_changes_docs_syncs_them(client, configure, calls):
    configure(private=False)
    from ohara import main

    asyncio.run(main.check_code(push("acme/api", ["docs/a.md"], before="0" * 40)))
    asyncio.run(main.check_code(push("acme/api", ["src/a.py"], before="0" * 40)))
    asyncio.run(main.check_code(push("acme/api", [".ohara.yml"], before="0" * 40)))
    assert calls == [("sync", "acme/api", "b" * 40), ("sync", "acme/api", "b" * 40)]


def test_hand_edits_to_a_synced_folder_are_synced_again(client, configure, calls):
    configure(private=False)
    db.put("app", "acme/api", {"name": "api", "branch": "main", "paths": ["docs"], "skipped": None})
    send(client, "push", push(REPO, ["apps/api/a.md", "apps/unknown/b.md", "guide.md"]))
    assert calls == [("sync", "acme/api", None)]


def test_the_apps_own_sync_commits_are_left_alone(client, configure, calls):
    configure(private=False)
    db.put("app", "acme/api", {"name": "api", "branch": "main", "paths": ["docs"], "skipped": None})
    send(client, "push", push(REPO, ["apps/api/a.md"], sender="ohara-docs[bot]"))
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


@respx.mock
def test_a_missing_commit_never_deletes_the_folder(configure):
    configure(private=False)
    routes = mock_sync({}, {"apps/api/a.md": "sha"})
    respx.get(url__regex=rf"{CODE}/git/trees/.*").mock(return_value=httpx.Response(404))
    with pytest.raises(httpx.HTTPStatusError):
        run_sync("gone")
    assert not routes["trees"].called


@respx.mock
def test_a_truncated_tree_never_deletes_files(configure):
    configure(private=False)
    routes = mock_sync({}, {"apps/api/a.md": "sha"})
    respx.get(url__regex=rf"{CODE}/git/trees/.*").mock(return_value=httpx.Response(200, json={"tree": [], "truncated": True}))
    with pytest.raises(ValueError):
        run_sync()
    assert not routes["trees"].called


@respx.mock
def test_an_empty_repository_has_no_docs(configure):
    configure(private=False)
    routes = mock_sync({}, {"apps/api/a.md": "sha"})
    respx.get(url__regex=rf"{CODE}/git/trees/.*").mock(return_value=httpx.Response(409))
    run_sync()
    assert written(routes) == {"apps/api/a.md": None}
