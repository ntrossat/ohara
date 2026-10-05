"""Instance settings saved in the data volume: GitHub App credentials and the docs repository."""

import json
import os
from pathlib import Path

from ohara.config import data_dir


def path():
    return data_dir() / "settings.json"


def load() -> dict:
    try:
        return json.loads(path().read_text())
    except FileNotFoundError:
        return {}


def save(settings: dict) -> None:
    write_private(path(), settings)


def write_private(target: Path, data) -> None:
    """Write JSON readable only by the owner, atomically."""
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, indent=2)
    tmp.replace(target)


def update(**values) -> dict:
    settings = load() | values
    save(settings)
    return settings


def configured(settings: dict | None = None) -> bool:
    settings = load() if settings is None else settings
    return bool(settings.get("app") and settings.get("repo"))

