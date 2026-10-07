"""Which docs of a code repository Ohara syncs into the docs repository, from its `.ohara.yml`:

    docs:                     # folders and files to sync, from the repository root
      - docs                  # a folder's contents go to the root of apps/<repo>/
      - README.md             # a file goes to the root by its name

A repository opts in by adding the file: without it, nothing is synced. A file without a `docs` list syncs
`docs/`, and an empty list syncs nothing.
"""

import posixpath

import yaml

FILE = ".ohara.yml"
DEFAULT = ["docs"]  # when the file has no docs list


class Invalid(Exception):
    """The config file can't be read: Ohara keeps the last synced copy."""


def parse(text: str | None) -> list[str]:
    """The paths to sync, none without a config file. Absolute paths and paths with `..` are dropped."""
    if text is None:
        return []
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise Invalid(f"{FILE} is not valid YAML: {error}")
    if data is None:
        return DEFAULT
    if not isinstance(data, dict):
        raise Invalid(f"{FILE} must be a mapping with a docs list")
    if "docs" not in data:
        return DEFAULT
    entries = data["docs"] or []
    if not isinstance(entries, list):
        raise Invalid(f"{FILE}: docs must be a list of paths")
    paths = []
    for entry in entries:
        path = posixpath.normpath(str(entry).strip()) if str(entry).strip() else ""
        if path and path != "." and not path.startswith(("/", "..")) and path not in paths:
            paths.append(path)
    return paths


def matches(paths: list[str], file: str) -> bool:
    """Whether a changed file is one of the synced paths, or inside one."""
    return file == FILE or any(file == path or file.startswith(f"{path}/") for path in paths)


def layout(paths: list[str], files: list[str]) -> dict[str, str]:
    """Where each synced file goes under apps/<repo>/, from the repository's file list: target to source.

    A folder's contents go to the root, a file goes to the root by its name. When two files land on the
    same target, the first entry wins.
    """
    targets = {}
    for path in paths:
        if path in files:
            targets.setdefault(posixpath.basename(path), path)
            continue
        for file in files:
            if file.startswith(f"{path}/"):
                targets.setdefault(file[len(path) + 1:], file)
    return targets
