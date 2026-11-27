import json

import httpx
import pytest
import respx

from ohara import changes
from tests.conftest import REPO
from tests.test_access import REPO_URL, sign_in

PULL = {
    "number": 7,
    "title": "Update billing",
    "body": "The Charges API is gone.\n\n---\nProposed through Ohara by @ada.",
    "user": {"login": "ohara-docs[bot]"},
    "head": {"ref": "api/billing", "sha": "head1"},
    "base": {"sha": "base1"},
    "state": "open",
    "updated_at": "2026-11-20T10:00:00Z",
    "html_url": f"https://github.com/{REPO}/pull/7",
}


@pytest.fixture(autouse=True)
def fresh_list():
    changes.forget()


@pytest.fixture
def installation():
    respx.post("https://api.github.com/app/installations/42/access_tokens").mock(
        return_value=httpx.Response(201, json={"token": "ghs_1"})
    )


def mock_pull(files, texts):
    """Mock pull request 7: `files` as the compare API lists them, `texts` as (path, ref) to file text."""
    respx.get(f"{REPO_URL}/pulls/7").mock(return_value=httpx.Response(200, json=PULL))
    respx.get(f"{REPO_URL}/compare/base1...head1").mock(
        return_value=httpx.Response(200, json={"merge_base_commit": {"sha": "fork1"}, "files": files})
    )
    for (path, ref), text in texts.items():
        respx.get(f"{REPO_URL}/contents/{path}", params={"ref": ref}).mock(return_value=httpx.Response(200, text=text))


@respx.mock
def test_readers_list_open_changes_with_who_proposed_them(client, configure, installation):
    configure(private=False)
    route = respx.get(f"{REPO_URL}/pulls").mock(return_value=httpx.Response(200, json=[PULL]))
    listed = client.get("/api/changes").json()
    assert listed == [
        {
            "number": 7,
            "title": "Update billing",
            "author": "ada",
            "branch": "api/billing",
            "draft": False,
            "updated_at": "2026-11-20T10:00:00Z",
            "html_url": f"https://github.com/{REPO}/pull/7",
        }
    ]
    client.get("/api/changes")
    assert route.call_count == 1  # kept for a minute


def test_private_changes_require_sign_in(client, configure):
    configure(private=True)
    assert client.get("/api/changes").status_code == 401
    assert client.get("/api/changes/7").status_code == 401
    assert client.post("/api/changes/7/approve", json={"sha": "head1"}).status_code == 401


@respx.mock
def test_a_change_shows_each_page_before_and_after(client, configure, installation):
    configure(private=False)
    mock_pull(
        [
            {"filename": "billing.md", "status": "modified"},
            {"filename": "new.md", "status": "added"},
            {"filename": "old.md", "status": "removed"},
            {"filename": "logo.svg", "status": "modified"},
        ],
        {
            ("billing.md", "fork1"): "---\nverified: 2026-01-01\n---\n# Billing\n\nCharges API.",
            ("billing.md", "head1"): "---\nverified: 2026-11-20\n---\n# Billing\n\nPaymentIntents API.",
            ("new.md", "head1"): "# New",
            ("old.md", "fork1"): "# Old",
        },
    )
    change = client.get("/api/changes/7").json()
    assert change["author"] == "ada"
    assert change["description"] == "The Charges API is gone."
    assert change["state"] == "open"
    assert change["sha"] == "head1"
    assert change["can_approve"] is False
    assert change["files"] == [
        {"file": "billing.md", "status": "changed", "before": "# Billing\n\nCharges API.", "after": "# Billing\n\nPaymentIntents API."},
        {"file": "new.md", "status": "added", "before": None, "after": "# New"},
        {"file": "old.md", "status": "removed", "before": "# Old", "after": None},
        {"file": "logo.svg", "status": "changed", "before": None, "after": None},
    ]


@respx.mock
def test_a_missing_change_is_not_found(client, configure, installation):
    configure(private=False)
    respx.get(f"{REPO_URL}/pulls/9").mock(return_value=httpx.Response(404))
    assert client.get("/api/changes/9").status_code == 404


@respx.mock
def test_a_writer_can_approve(client, configure, installation):
    configure(private=False)
    mock_pull([], {})
    respx.get(REPO_URL).mock(return_value=httpx.Response(200, json={"permissions": {"push": True}}))
    client.cookies.set("ohara_session", sign_in())
    assert client.get("/api/changes/7").json()["can_approve"] is True


@respx.mock
def test_approving_merges_as_the_user_and_rebuilds(client, configure, synced):
    configure(private=True)
    respx.get(REPO_URL).mock(
        return_value=httpx.Response(200, json={"permissions": {"push": True}, "allow_merge_commit": False, "allow_squash_merge": True})
    )
    merge = respx.put(f"{REPO_URL}/pulls/7/merge").mock(return_value=httpx.Response(200, json={"merged": True}))
    client.cookies.set("ohara_session", sign_in())
    assert client.post("/api/changes/7/approve", json={"sha": "head1"}).json() == {"merged": True}
    assert merge.calls.last.request.headers["Authorization"] == "Bearer ghu_1"
    assert json.loads(merge.calls.last.request.content) == {"sha": "head1", "merge_method": "squash"}
    assert synced == [True]


@respx.mock
def test_approving_needs_write_access(client, configure):
    configure(private=True)
    respx.get(REPO_URL).mock(return_value=httpx.Response(200, json={"permissions": {"push": False}}))
    merge = respx.put(f"{REPO_URL}/pulls/7/merge")
    client.cookies.set("ohara_session", sign_in())
    assert client.post("/api/changes/7/approve", json={"sha": "head1"}).status_code == 403
    assert not merge.called


@respx.mock
def test_approving_a_change_that_moved_on_is_refused(client, configure, synced):
    configure(private=True)
    respx.get(REPO_URL).mock(return_value=httpx.Response(200, json={"permissions": {"push": True}}))
    respx.put(f"{REPO_URL}/pulls/7/merge").mock(return_value=httpx.Response(409, json={"message": "Head branch was modified"}))
    client.cookies.set("ohara_session", sign_in())
    refused = client.post("/api/changes/7/approve", json={"sha": "stale"})
    assert refused.status_code == 409
    assert "reload" in refused.json()["detail"]
    assert synced == []


@respx.mock
def test_a_change_github_cannot_merge_says_why(client, configure):
    configure(private=True)
    respx.get(REPO_URL).mock(return_value=httpx.Response(200, json={"permissions": {"push": True}}))
    respx.put(f"{REPO_URL}/pulls/7/merge").mock(
        return_value=httpx.Response(405, json={"message": "At least 1 approving review is required."})
    )
    client.cookies.set("ohara_session", sign_in())
    refused = client.post("/api/changes/7/approve", json={"sha": "head1"})
    assert refused.status_code == 409
    assert "At least 1 approving review is required" in refused.json()["detail"]
