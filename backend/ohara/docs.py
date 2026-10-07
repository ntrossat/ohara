"""Docs snapshot: extraction from a GitHub tarball, navigation, and page lookup.

The folder tree is the navigation. A page's title comes from front matter
`title`, then its first `# ` heading, then its file name. Pages are
sorted by title. Each snapshot is indexed for full-text search.
"""

import io
import re
import shutil
import tarfile
from collections.abc import Iterator
from pathlib import Path

import yaml

from ohara import db

INDEX_NAMES = ("index.md", "README.md")
FRONT_MATTER = re.compile(r"\A---\n(.*?)\n---\n?", re.S)
HEADING = re.compile(r"^#\s+(.+?)\s*#*\s*$", re.M)


def parse(text: str) -> tuple[dict, str]:
    match = FRONT_MATTER.match(text)
    if not match:
        return {}, text
    try:
        meta = yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        return {}, text
    if not isinstance(meta, dict):
        return {}, text
    return meta, text[match.end():]


def humanize(name: str) -> str:
    words = re.sub(r"[-_]+", " ", name).strip()
    return words[:1].upper() + words[1:]


def page_info(path: Path) -> tuple[dict, str, str]:
    meta, body = parse(path.read_text(errors="replace"))
    heading = HEADING.search(body)
    fallback = humanize(path.parent.name if path.name in INDEX_NAMES else path.stem)
    title = str(meta.get("title") or (heading.group(1) if heading else fallback))
    return meta, body, title


def index_of(folder: Path) -> Path | None:
    for name in INDEX_NAMES:
        if (folder / name).is_file():
            return folder / name
    return None


def build_nav(root: Path, folder: Path | None = None) -> list[dict]:
    folder = folder or root
    nodes = []
    for entry in folder.iterdir():
        if entry.name.startswith("."):
            continue
        rel = entry.relative_to(root).as_posix()
        if entry.is_dir():
            children = build_nav(root, entry)
            index = index_of(entry)
            if not children and not index:
                continue
            title = page_info(index)[2] if index else humanize(entry.name)
            nodes.append({"title": title, "path": rel if index else None, "folder": rel, "children": children})
        elif entry.suffix == ".md" and entry.name not in INDEX_NAMES:
            nodes.append({"title": page_info(entry)[2], "path": rel[:-3], "children": []})
    return sorted(nodes, key=lambda node: node["title"].lower())


def resolve_file(root: Path, rel: str) -> Path | None:
    root = root.resolve()
    path = (root / rel).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        return None
    if any(part.startswith(".") for part in path.relative_to(root).parts):
        return None
    return path


def read_page(root: Path, path: str) -> dict | None:
    path = path.strip("/")
    candidates = [f"{path}.md"] if path else []
    candidates += [f"{path}/{name}".lstrip("/") for name in INDEX_NAMES]
    for candidate in candidates:
        file = resolve_file(root, candidate)
        if file:
            meta, body, title = page_info(file)
            return {"title": title, "file": candidate, "markdown": body, "meta": meta}
    return None


def extract(tarball: bytes, root: Path) -> None:
    """Replace the snapshot at `root` with the regular files of a GitHub tarball."""
    staging = root.with_name(root.name + ".new")
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(tarball), mode="r:gz") as tar:
        for member in tar.getmembers():
            parts = Path(member.name).parts[1:]  # drop GitHub's "owner-repo-sha/" prefix
            if not member.isfile() or not parts or ".." in parts:
                continue
            target = staging.joinpath(*parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(tar.extractfile(member).read())
    old = root.with_name(root.name + ".old")
    shutil.rmtree(old, ignore_errors=True)
    if root.exists():
        root.rename(old)
    staging.rename(root)
    shutil.rmtree(old, ignore_errors=True)


def page_path(rel: Path) -> str:
    """The page path of a Markdown file: no extension, and a folder for its index page."""
    if rel.name in INDEX_NAMES:
        return rel.parent.as_posix().removeprefix(".")
    return rel.as_posix()[:-3]


def pages(root: Path) -> Iterator[tuple[str, str, dict]]:
    """Every page of the snapshot as (page path, file relative to root, front matter)."""
    for file in sorted(root.rglob("*.md")) if root.exists() else []:
        rel = file.relative_to(root)
        if not any(part.startswith(".") for part in rel.parts):
            yield page_path(rel), rel.as_posix(), page_info(file)[0]


def index(root: Path) -> None:
    """Replace the search index with the pages of the snapshot at `root`."""
    rows = []
    for path, file, _ in pages(root):
        _, body, title = page_info(root / file)
        rows.append((path, title, " ".join(HEADING.sub("", body, count=1).split())))
    db.replace_pages(rows)


def search(query: str, limit: int) -> list[dict]:
    """Pages containing every word of the query, best matches first. Titles weigh more than text."""
    words = query.split()
    if not words:
        return []
    return [{"path": path, "title": title, "snippet": snippet} for path, title, snippet in db.search_pages(words, limit)]
