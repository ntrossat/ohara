import datetime

import httpx
import respx

from ohara import docs, freshness
from tests.test_mcp import call, result
from tests.test_webhook import post

COVERED = "---\nowner: ada\nverified: {verified}\ncovers: [acme/api:src/billing/*]\n---\n# Billing\n\nInvoices go out monthly."


def write_billing(data_dir, verified=None):
    verified = verified or datetime.date.today().isoformat()
    (data_dir / "docs" / "billing.md").write_text(COVERED.format(verified=verified))
    docs.index(data_dir / "docs")


def code_push(before="a" * 40, after="b" * 40, repo="acme/api"):
    return {
        "ref": "refs/heads/main",
        "before": before,
        "after": after,
        "repository": {"full_name": repo, "default_branch": "main"},
        "installation": {"id": 42},
        "commits": [{"added": ["src/billing/tax.py"], "modified": [], "removed": []}],
    }


def mock_compare(files):
    respx.post("https://api.github.com/app/installations/42/access_tokens").mock(return_value=httpx.Response(201, json={"token": "ghs_app"}))
    return respx.get(f"https://api.github.com/repos/acme/api/compare/{'a' * 40}...{'b' * 40}").mock(
        return_value=httpx.Response(200, json={"files": [{"filename": name} for name in files]})
    )


def test_fresh_page_reports_owner_and_verified_date(mcp, configure, data_dir):
    configure(private=False)
    write_billing(data_dir, "2026-01-02")
    page = result(call(mcp, "read_page", path="billing"))["structuredContent"]
    assert page["owner"] == "ada"
    assert page["verified"] == "2026-01-02"
    assert page["covers"] == ["acme/api:src/billing/*"]


def test_page_not_verified_for_long_is_stale(mcp, configure, data_dir):
    configure(private=False)
    old = (datetime.date.today() - datetime.timedelta(days=freshness.STALE_AFTER_DAYS + 1)).isoformat()
    write_billing(data_dir, old)
    page = result(call(mcp, "read_page", path="billing"))["structuredContent"]
    assert page["stale"] == [f"Not verified since {old}"]
    assert [found["path"] for found in result(call(mcp, "stale_pages"))["structuredContent"]["result"]] == ["billing"]


@respx.mock
def test_push_to_covered_code_flags_the_page_until_it_changes(client, configure, data_dir, synced):
    configure(private=False)
    write_billing(data_dir)
    mock_compare(["src/billing/invoice.py", "src/auth/login.py"])
    assert post(client, code_push()).json() == {"synced": False, "checked": True}
    assert synced == []

    page = docs.read_page(data_dir / "docs", "billing")
    stale = freshness.status(data_dir / "docs", page)["stale"]
    assert len(stale) == 1 and "acme/api" in stale[0] and "src/billing/invoice.py" in stale[0]
    assert "src/auth" not in stale[0]

    (data_dir / "docs" / "billing.md").write_text(COVERED.format(verified="2026-10-05") + "\nUpdated.")
    page = docs.read_page(data_dir / "docs", "billing")
    assert freshness.status(data_dir / "docs", page)["stale"] == []


@respx.mock
def test_push_to_other_code_flags_nothing(client, configure, data_dir, synced):
    configure(private=False)
    write_billing(data_dir)
    mock_compare(["src/auth/login.py"])
    post(client, code_push())
    assert freshness.stale_pages(data_dir / "docs") == []


def test_new_branch_push_uses_the_commit_file_lists(client, configure, data_dir, synced):
    configure(private=False)
    write_billing(data_dir)
    post(client, code_push(before="0" * 40))
    assert freshness.stale_pages(data_dir / "docs")[0]["path"] == "billing"


def test_push_to_another_branch_of_code_is_ignored(client, configure, synced):
    configure(private=False)
    assert post(client, code_push() | {"ref": "refs/heads/feature"}).json() == {"synced": False}


def test_stamp_verified_keeps_the_rest_of_the_front_matter():
    day = datetime.date(2026, 10, 5)
    assert freshness.stamp_verified("# Page", day) == "---\nverified: 2026-10-05\n---\n\n# Page"
    assert freshness.stamp_verified("---\nowner: ada\n---\n# Page", day) == "---\nowner: ada\nverified: 2026-10-05\n---\n# Page"
    assert freshness.stamp_verified("---\nverified: 2020-01-01\norder: 2\n---\n# Page", day) == "---\nverified: 2026-10-05\norder: 2\n---\n# Page"


def test_covers_reads_repository_patterns():
    assert freshness.covers({"covers": "Acme/API:/src/*"}) == [("acme/api", "src/*")]
    assert freshness.covers({"covers": ["acme/api:src/*", "no-repository", 3]}) == [("acme/api", "src/*")]
    assert freshness.covers({}) == []
