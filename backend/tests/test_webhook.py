import hashlib
import hmac
import json

import respx

from tests.conftest import REPO


def post(client, payload, event="push", secret="hook-secret", signature=None):
    body = json.dumps(payload).encode()
    signature = signature or "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return client.post(
        "/api/github/webhook",
        content=body,
        headers={"X-GitHub-Event": event, "X-Hub-Signature-256": signature, "Content-Type": "application/json"},
    )


def test_push_to_default_branch_triggers_sync(client, configure, synced):
    configure()
    response = post(client, {"ref": "refs/heads/main", "repository": {"full_name": REPO}})
    assert response.json() == {"synced": True}
    assert synced == [True]


def test_push_to_other_branch_is_ignored(client, configure, synced):
    configure()
    post(client, {"ref": "refs/heads/feature", "repository": {"full_name": REPO}})
    assert synced == []


def test_repository_visibility_change_triggers_sync(client, configure, synced):
    configure()
    post(client, {"action": "privatized", "repository": {"full_name": REPO}}, event="repository")
    assert synced == [True]


def test_other_repository_is_ignored(client, configure, synced):
    configure()
    post(client, {"ref": "refs/heads/main", "repository": {"full_name": "acme/other"}})
    assert synced == []


def test_bad_or_missing_signature_is_rejected(client, configure, synced):
    configure()
    payload = {"ref": "refs/heads/main", "repository": {"full_name": REPO}}
    assert post(client, payload, secret="wrong").status_code == 401
    assert client.post("/api/github/webhook", json=payload).status_code == 401
    assert synced == []


@respx.mock
def test_merged_code_pull_request_leaves_its_docs_pull_request_for_review(client, configure, synced):
    configure()
    payload = {
        "action": "closed",
        "repository": {"full_name": "acme/api", "name": "api", "default_branch": "main"},
        "installation": {"id": 42},
        "pull_request": {"merged": True, "base": {"ref": "main"}, "head": {"ref": "feature/billing"}},
    }
    assert post(client, payload, event="pull_request").json() == {"synced": False}
    assert not respx.calls  # Ohara never merges or closes a docs pull request
    assert synced == []
