import hashlib
import hmac
import json

import pytest

from ohara import main
from tests.conftest import REPO


@pytest.fixture
def synced(monkeypatch):
    calls = []

    async def fake_sync():
        calls.append(True)

    monkeypatch.setattr(main, "safe_sync", fake_sync)
    return calls


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
