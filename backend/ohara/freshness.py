"""Page freshness: who owns a page, when a human last verified it, and whether the code it describes changed since.

Front matter, all optional:
    owner: ada                         # who keeps the page up to date
    verified: 2026-03-01               # set on every change proposed through Ohara, so merging it verifies the page
    covers: [acme/api:src/billing/*]   # code the page describes, as repository:pattern

A page is stale when it was verified more than STALE_AFTER_DAYS ago, or when a push to the default
branch of a covered repository changed matching files. A code change flag lasts until the page itself changes.
In patterns, `*` also matches across folders.
"""

import datetime
import fnmatch
import hashlib
import re
import time
from pathlib import Path

from ohara import db, docs

STALE_AFTER_DAYS = 180
MAX_CHANGES = 20  # code changes kept per page
DRIFT_TTL = 365 * 24 * 3600  # flags of deleted pages do not linger


def _hash(file: Path) -> str:
    return hashlib.sha256(file.read_bytes()).hexdigest()


def _date(value) -> datetime.date | None:
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    try:
        return datetime.date.fromisoformat(str(value))
    except ValueError:
        return None


def covers(meta: dict) -> list[tuple[str, str]]:
    """(repository, pattern) pairs from the `covers` front matter."""
    values = meta.get("covers") or []
    pairs = []
    for value in [values] if isinstance(values, str) else values:
        repo, sep, pattern = str(value).partition(":")
        if sep and repo and pattern:
            pairs.append((repo.lower(), pattern.lstrip("/")))
    return pairs


def status(root: Path, page: dict) -> dict:
    """Freshness of a page from docs.read_page: owner, verified date, covered code, and why it is stale (empty when fresh)."""
    meta = page["meta"]
    verified = _date(meta.get("verified")) if meta.get("verified") else None
    reasons = []
    if verified and (datetime.date.today() - verified).days > STALE_AFTER_DAYS:
        reasons.append(f"Not verified since {verified.isoformat()}")
    drift = db.get("drift", page["file"])
    if drift and drift["hash"] == _hash(root / page["file"]):
        for change in drift["changes"]:
            files = ", ".join(change["files"][:5]) + (" and more" if len(change["files"]) > 5 else "")
            reasons.append(f"Code changed in {change['repo']} on {change['at']} ({change['compare']}): {files}")
    owner = meta.get("owner")
    return {
        "owner": str(owner) if owner else None,
        "verified": verified.isoformat() if verified else None,
        "covers": [f"{repo}:{pattern}" for repo, pattern in covers(meta)],
        "stale": reasons,
    }


def stale_pages(root: Path) -> list[dict]:
    pages = []
    for path, file, _ in docs.pages(root):
        page = docs.read_page(root, path)
        found = status(root, page)
        if found["stale"]:
            pages.append({"path": path, "title": page["title"]} | found)
    return pages


def record_push(root: Path, repo: str, files: list[str], compare: str) -> list[str]:
    """Flag the pages whose covered code changed in this push. Returns their paths."""
    repo = repo.lower()
    flagged = []
    for path, file, meta in docs.pages(root):
        patterns = [pattern for covered, pattern in covers(meta) if covered == repo]
        matched = [name for name in files if any(fnmatch.fnmatch(name, pattern) for pattern in patterns)]
        if not matched:
            continue
        current = _hash(root / file)
        drift = db.get("drift", file)
        if not drift or drift["hash"] != current:
            drift = {"hash": current, "changes": []}
        change = {"repo": repo, "at": datetime.date.today().isoformat(), "compare": compare, "files": matched}
        drift["changes"] = [*drift["changes"], change][-MAX_CHANGES:]
        db.put("drift", file, drift, time.time() + DRIFT_TTL)
        flagged.append(path)
    return flagged


def set_field(markdown: str, key: str, value: str) -> str:
    """Set one front matter field, keeping the rest of the front matter as written."""
    line = f"{key}: {value}"
    pattern = re.compile(rf"^{re.escape(key)}:.*$", re.M)
    match = docs.FRONT_MATTER.match(markdown)
    if not match:
        return f"---\n{line}\n---\n\n{markdown}"
    block = match.group(1)
    block = pattern.sub(lambda _: line, block) if pattern.search(block) else f"{block}\n{line}"
    return f"---\n{block}\n---\n{markdown[match.end():]}"


def remove_field(markdown: str, key: str) -> str:
    """Remove one front matter field, and the front matter when nothing else is left in it."""
    match = docs.FRONT_MATTER.match(markdown)
    if not match:
        return markdown
    block = re.sub(rf"^{re.escape(key)}:.*(\n|$)", "", match.group(1), flags=re.M).strip("\n")
    body = markdown[match.end():]
    return f"---\n{block}\n---\n{body}" if block.strip() else body.lstrip("\n")


def stamp_verified(markdown: str, day: datetime.date) -> str:
    """Set `verified` in the page's front matter, keeping the rest of it as written."""
    return set_field(markdown, "verified", day.isoformat())
