import json

import httpx
import respx

from ohara import codeowners, docs, mcp_server
from tests.conftest import REPO, tarball
from tests.test_webhook import post

API = "https://api.github.com"
DOCS = f"{API}/repos/{REPO}"
CODE_PULL = "https://github.com/acme/api/pull/3"


def test_rules_follow_github_patterns():
    rules = codeowners.parse(
        "# Reviewed folders\n"
        "/guidelines/  @acme/architects\n"
        "*.svg         @acme/design\n"
        "team/*        @acme/leads\n"
        "/guidelines/drafts/\n"
    )
    assert codeowners.needs_review(rules, "guidelines/api.md")
    assert codeowners.needs_review(rules, "guidelines/web/react.md")
    assert codeowners.needs_review(rules, "design/logo.svg")
    assert codeowners.needs_review(rules, "team/oncall.md")
    assert not codeowners.needs_review(rules, "team/billing/invoices.md")  # team/* only matches its own files
    assert not codeowners.needs_review(rules, "guidelines/drafts/new.md")  # the last matching rule wins
    assert not codeowners.needs_review(rules, "architecture/web.md")


def test_a_catch_all_rule_reviews_everything():
    rules = codeowners.parse("* @acme/docs\n/architecture/\n")
    assert codeowners.needs_review(rules, "README.md")
    assert not codeowners.needs_review(rules, "architecture/web/deployment.md")


def test_without_codeowners_everything_needs_review(tmp_path):
    assert codeowners.load(tmp_path) is None
    assert codeowners.needs_review(None, "architecture/web.md")
    (tmp_path / "CODEOWNERS").write_text("/design/ @acme/design\n")
    assert codeowners.needs_review(codeowners.load(tmp_path), "design/brand.md")


def test_the_snapshot_keeps_github_codeowners(tmp_path):
    docs.extract(tarball({".github/CODEOWNERS": "/design/ @acme/design\n", "README.md": "# Home"}), tmp_path / "docs")
    assert codeowners.needs_review(codeowners.load(tmp_path / "docs"), "design/brand.md")


def test_code_branch_uses_the_repository_name():
    assert mcp_server.code_branch("acme/api", "feature/billing") == mcp_server.code_branch("api", "feature/billing") == "api/feature/billing"
    assert mcp_server.code_branch("", "main") is None


def code_pull(merged=True, base="main", head="feature/billing"):
    return {
        "action": "closed",
        "repository": {"full_name": "acme/api", "name": "api", "default_branch": "main"},
        "installation": {"id": 42},
        "pull_request": {"merged": merged, "html_url": CODE_PULL, "base": {"ref": base}, "head": {"ref": head}},
    }


def mock_docs_pull(files):
    respx.post(f"{API}/app/installations/42/access_tokens").mock(return_value=httpx.Response(201, json={"token": "ghs_app"}))
    find = respx.get(f"{DOCS}/pulls").mock(
        return_value=httpx.Response(200, json=[{"number": 9, "html_url": "https://github.com/acme/handbook/pull/9", "head": {"sha": "docs-sha"}}])
    )
    respx.get(f"{DOCS}/pulls/9/files").mock(return_value=httpx.Response(200, json=[{"filename": name} for name in files]))
    merge = respx.put(f"{DOCS}/pulls/9/merge").mock(return_value=httpx.Response(200, json={"merged": True}))
    close = respx.patch(f"{DOCS}/pulls/9").mock(return_value=httpx.Response(200, json={}))
    comment = respx.post(f"{DOCS}/issues/9/comments").mock(return_value=httpx.Response(201, json={}))
    return find, merge, close, comment


def owners(data_dir):
    (data_dir / "docs" / "CODEOWNERS").write_text("/guidelines/ @acme/architects\n")


@respx.mock
def test_merged_code_merges_its_docs_pull_request(client, configure, data_dir, synced):
    configure(private=False)
    owners(data_dir)
    find, merge, close, _ = mock_docs_pull(["architecture/billing.md"])
    assert post(client, code_pull(), event="pull_request").json() == {"synced": False, "followed": True}
    assert find.calls.last.request.url.params["head"] == "acme:api/feature/billing"
    assert json.loads(merge.calls.last.request.content) == {"merge_method": "squash", "sha": "docs-sha"}
    assert not close.called


@respx.mock
def test_merged_code_leaves_owned_pages_for_review(client, configure, data_dir, synced):
    configure(private=False)
    owners(data_dir)
    _, merge, _, comment = mock_docs_pull(["architecture/billing.md", "guidelines/api.md"])
    post(client, code_pull(), event="pull_request")
    assert not merge.called
    assert "guidelines/api.md" in json.loads(comment.calls.last.request.content)["body"]


@respx.mock
def test_merged_code_without_codeowners_leaves_everything_for_review(client, configure, data_dir, synced):
    configure(private=False)
    _, merge, _, comment = mock_docs_pull(["architecture/billing.md"])
    post(client, code_pull(), event="pull_request")
    assert not merge.called
    assert "no CODEOWNERS file" in json.loads(comment.calls.last.request.content)["body"]


@respx.mock
def test_merged_code_reports_a_refused_merge(client, configure, data_dir, synced):
    configure(private=False)
    owners(data_dir)
    _, merge, _, comment = mock_docs_pull(["architecture/billing.md"])
    merge.mock(return_value=httpx.Response(405, json={"message": "Pull Request is not mergeable"}))
    post(client, code_pull(), event="pull_request")
    assert "not mergeable" in json.loads(comment.calls.last.request.content)["body"]


@respx.mock
def test_closed_code_closes_its_docs_pull_request(client, configure, data_dir, synced):
    configure(private=False)
    owners(data_dir)
    _, merge, close, comment = mock_docs_pull(["architecture/billing.md"])
    post(client, code_pull(merged=False), event="pull_request")
    assert json.loads(close.calls.last.request.content) == {"state": "closed"}
    assert CODE_PULL in json.loads(comment.calls.last.request.content)["body"]
    assert not merge.called


def test_code_merged_into_another_branch_is_ignored(client, configure, synced):
    configure(private=False)
    assert post(client, code_pull(base="release"), event="pull_request").json() == {"synced": False}
