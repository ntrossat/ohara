"""App docs: the docs that live in code repositories, shown under apps/<repo>/ of the website.

The code repository is the source of truth: each sync downloads it and replaces its apps/<repo>/ folder in the
local docs snapshot. Nothing is written to the docs repository. Each synced page gets a `source` front matter
field ("owner/repo:path") that points to its file in the code repository.

A code repository opts in with a `.ohara.yml`, which lists the files to sync (see appconfig.py). A private code
repository is never synced into a public docs repository: the website would publish its docs.
"""

import asyncio
import io
import logging
import posixpath
import shutil
import tarfile
from pathlib import Path

from ohara import appconfig, config, db, docs, freshness, github

TYPES = (".md", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp")
MAX_SIZE = 1_000_000  # bytes per file
MAX_FILES = 500

log = logging.getLogger("ohara")


def folder(name: str) -> str:
    return f"{docs.APPS}/{name}"


def synced(path: str) -> bool:
    return path.startswith(f"{docs.APPS}/")


def state(full_name: str) -> dict | None:
    """The last sync of a code repository: its folder name, branch and paths, or why it was skipped."""
    return db.get("app", full_name.lower())


def private_into_public(code_private: bool, settings: dict) -> bool:
    return code_private and not settings["repo"]["private"]


async def sync(settings: dict, full_name: str, ref: str | None = None) -> None:
    """Replace the apps/<repo>/ folder of the snapshot with a code repository's docs at `ref`."""
    if full_name.lower() == settings["repo"]["full_name"].lower():
        return
    token = await github.installation_token(settings["app"], settings["installation_id"])
    code = await github.get_repo(token, full_name)
    name, ref = code["name"], ref or code["default_branch"]
    record = {"name": name, "branch": code["default_branch"], "paths": [], "skipped": None}
    files = {}
    if private_into_public(code["private"], settings):
        # Nothing is synced, and a copy from when the docs repository was private is removed.
        record["skipped"] = f"{full_name} is private and {settings['repo']['full_name']} is public, so its docs are not synced"
        log.warning(record["skipped"])
    else:
        try:
            record["paths"] = appconfig.parse(await github.get_file(token, full_name, appconfig.FILE, ref))
        except appconfig.Invalid as error:
            db.put("app", full_name.lower(), (state(full_name) or record) | {"skipped": f"{error}. The last synced copy stays"})
            log.warning("%s: %s", full_name, error)
            return
        if record["paths"]:
            archive = await github.tarball(token, full_name, ref)
            files = await asyncio.to_thread(read, archive, full_name, record["paths"])
    async with docs.lock:
        await asyncio.to_thread(write, config.docs_dir() / folder(name), files)
        db.put("app", full_name.lower(), record)
        await asyncio.to_thread(docs.index, config.docs_dir())
    log.info("synced %d files of %s@%s", len(files), full_name, ref[:12])


def read(archive: bytes, full_name: str, paths: list[str]) -> dict[str, bytes]:
    """The synced files of a repository tarball, by their path under apps/<repo>/."""
    found = {}
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
        for member in tar.getmembers():
            parts = Path(member.name).parts[1:]  # drop GitHub's "owner-repo-sha/" prefix
            path = "/".join(parts)
            hidden = any(part.startswith(".") for part in parts)  # also drops ".."
            if member.isfile() and path.lower().endswith(TYPES) and member.size <= MAX_SIZE and not hidden:
                found[path] = member
        files = {}
        for target, source in list(appconfig.layout(paths, sorted(found)).items())[:MAX_FILES]:
            data = tar.extractfile(found[source]).read()
            if source.lower().endswith(".md"):
                data = freshness.set_field(data.decode(errors="replace"), "source", f'"{full_name}:{source}"').encode()
            files[target] = data
    return files


def write(target: Path, files: dict[str, bytes]) -> None:
    """Replace the folder at `target` with these files, or remove it when there are none."""
    if not files:
        shutil.rmtree(target, ignore_errors=True)
        return
    staging = target.with_name(f".{target.name}.new")
    shutil.rmtree(staging, ignore_errors=True)
    for path, data in files.items():
        file = staging / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(data)
    docs.swap(staging, target)


def orphans(root: Path, names: set[str]) -> list[str]:
    """The folders under apps/ in the snapshot that belong to no repository on the installation."""
    apps = root / docs.APPS
    folders = [entry.name for entry in apps.iterdir() if entry.is_dir()] if apps.is_dir() else []
    return sorted(name for name in folders if name not in names and not name.startswith("."))


async def remove(full_name: str) -> None:
    """Remove the synced folder of a code repository the app no longer has access to."""
    name = (state(full_name) or {}).get("name") or full_name.split("/")[-1]
    async with docs.lock:
        db.delete("app", full_name.lower())
        await asyncio.to_thread(write, config.docs_dir() / folder(name), {})
        await asyncio.to_thread(docs.index, config.docs_dir())


def needs_sync(full_name: str, files: list[str]) -> bool:
    """Whether a push that changed `files` changed the synced docs, from the paths of the last sync."""
    record = state(full_name)
    paths = record["paths"] if record and not record.get("skipped") else []
    return any(appconfig.matches(paths, posixpath.normpath(file)) for file in files)
