"""App docs: the docs that live in code repositories, synced into apps/<repo>/ of the docs repository.

The code repository is the source of truth: each sync replaces the whole apps/<repo>/ folder in one commit, so
renames, deletions and hand edits made in the docs repository are all overwritten. Each synced page gets a
`source` front matter field ("owner/repo:path") that points to its file in the code repository.

A code repository opts in with a `.ohara.yml`, which lists the files to sync (see appconfig.py). A private code
repository is never synced into a public docs repository: the website would publish its docs.
"""

import asyncio
import hashlib
import logging
import posixpath

from ohara import appconfig, config, db, freshness, github

APPS = "apps"
TYPES = (".md", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp")
MAX_SIZE = 1_000_000  # bytes per file
MAX_FILES = 500

log = logging.getLogger("ohara")
lock = asyncio.Lock()  # one sync at a time, so commits to the docs repository never race


def folder(name: str) -> str:
    return f"{APPS}/{name}"


def git_sha(data: bytes) -> str:
    """The blob sha Git gives this content, to skip files that didn't change."""
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def synced(path: str) -> bool:
    return path.startswith(f"{APPS}/")


def state(full_name: str) -> dict | None:
    """The last sync of a code repository: its folder name, branch and paths, or why it was skipped."""
    return db.get("app", full_name.lower())


def private_into_public(code_private: bool, settings: dict) -> bool:
    return code_private and not settings["repo"]["private"]


async def sync(settings: dict, full_name: str, ref: str | None = None) -> str | None:
    """Sync a code repository's docs into the docs repository. Returns the pull request URL when the docs
    repository's default branch is protected, else None."""
    docs_repo = settings["repo"]
    if full_name.lower() == docs_repo["full_name"].lower():
        return None
    async with lock:
        token = await github.installation_token(settings["app"], settings["installation_id"])
        code = await github.get_repo(token, full_name)
        name, ref = code["name"], ref or code["default_branch"]
        record = {"name": name, "branch": code["default_branch"], "paths": [], "skipped": None}
        if private_into_public(code["private"], settings):
            # Nothing is synced, and a copy from when the docs repository was private is removed.
            record["skipped"] = f"{full_name} is private and {docs_repo['full_name']} is public, so its docs are not synced"
            log.warning(record["skipped"])
            paths = []
        else:
            try:
                paths = appconfig.parse(await github.get_file(token, full_name, appconfig.FILE, ref))
            except appconfig.Invalid as error:
                previous = state(full_name) or record
                db.put("app", full_name.lower(), previous | {"skipped": f"{error}. The last synced copy stays"})
                log.warning("%s: %s", full_name, error)
                return None
            record["paths"] = paths
        files = {}
        for entry in await github.get_tree(token, full_name, ref) if paths else []:
            parts = entry["path"].split("/")
            regular = entry.get("mode") in ("100644", "100755")  # not a symbolic link
            if regular and entry["path"].lower().endswith(TYPES) and entry.get("size", 0) <= MAX_SIZE and not any(p.startswith(".") for p in parts):
                files[entry["path"]] = entry
        targets = list(appconfig.layout(paths, list(files)).items())[:MAX_FILES]
        wanted = {}
        for target, source in targets:
            data = await github.get_blob(token, full_name, files[source]["sha"])
            if source.lower().endswith(".md"):
                text = freshness.set_field(data.decode(errors="replace"), "source", f'"{full_name}:{source}"')
                data = text.encode()
            wanted[f"{folder(name)}/{target}"] = data
        if not wanted and not (config.docs_dir() / folder(name)).exists():  # nothing to sync, and nothing to remove
            db.put("app", full_name.lower(), record)
            return None
        current = {
            entry["path"]: entry["sha"]
            for entry in await github.get_tree(token, docs_repo["full_name"], docs_repo["default_branch"])
            if entry["path"].startswith(f"{folder(name)}/")
        }
        db.put("app", full_name.lower(), record)
        entries = []
        for path, data in wanted.items():
            if current.get(path) != git_sha(data):
                sha = await github.create_blob(token, docs_repo["full_name"], data)
                entries.append({"path": path, "mode": "100644", "type": "blob", "sha": sha})
        entries += [{"path": path, "mode": "100644", "type": "blob", "sha": None} for path in current if path not in wanted]
        if not entries:
            return None
        return await commit(token, docs_repo, name, entries, f"docs: sync {full_name}@{ref[:12]}")


def orphans(root, names: set[str]) -> list[str]:
    """The folders under apps/ in the snapshot that belong to no repository on the installation."""
    apps = root / APPS
    folders = [entry.name for entry in apps.iterdir() if entry.is_dir()] if apps.is_dir() else []
    return sorted(name for name in folders if name not in names and not name.startswith("."))


async def remove(settings: dict, full_name: str) -> str | None:
    """Delete the synced folder of a code repository the app no longer has access to."""
    docs_repo = settings["repo"]
    name = (state(full_name) or {}).get("name") or full_name.split("/")[-1]
    async with lock:
        db.delete("app", full_name.lower())
        token = await github.installation_token(settings["app"], settings["installation_id"])
        tree = await github.get_tree(token, docs_repo["full_name"], docs_repo["default_branch"])
        entries = [
            {"path": entry["path"], "mode": "100644", "type": "blob", "sha": None}
            for entry in tree
            if entry["path"].startswith(f"{folder(name)}/")
        ]
        if not entries:
            return None
        return await commit(token, docs_repo, name, entries, f"docs: remove the synced docs of {full_name}")


async def commit(token: str, docs_repo: dict, name: str, entries: list[dict], message: str) -> str | None:
    if await github.commit_tree(token, docs_repo["full_name"], docs_repo["default_branch"], entries, message):
        log.info(message)
        return None
    body = (
        f"Ohara could not commit to `{docs_repo['default_branch']}`, which is likely protected, so it opened this pull "
        f"request instead. The files in `{folder(name)}/` come from the code repository: merge it as is."
    )
    url = await github.open_tree_pull_request(
        token, docs_repo["full_name"], docs_repo["default_branch"], f"ohara/sync-{name}", entries, message, body
    )
    log.info("%s: %s", message, url)
    return url


def touched_by_hand(payload: dict, settings: dict) -> list[str]:
    """The code repositories whose synced folder a push to the docs repository changed, when the app didn't push it."""
    if (payload.get("sender") or {}).get("login") == f"{settings['app']['slug']}[bot]":
        return []
    names = set()
    for commit in payload.get("commits", []):
        for key in ("added", "modified", "removed"):
            for path in commit.get(key, []):
                parts = path.split("/")
                if len(parts) > 2 and parts[0] == APPS:
                    names.add(parts[1])
    known = {record["name"]: full_name for full_name, record in db.all("app").items() if record.get("name")}
    return sorted(known[name] for name in names if name in known)


def needs_sync(full_name: str, files: list[str]) -> bool:
    """Whether a push that changed `files` changed the synced docs, from the paths of the last sync."""
    record = state(full_name)
    paths = record["paths"] if record and not record.get("skipped") else []
    return any(appconfig.matches(paths, posixpath.normpath(file)) for file in files)
