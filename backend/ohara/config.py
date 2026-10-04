import os
from pathlib import Path


def base_url() -> str:
    return os.environ.get("OHARA_URL", "http://localhost:8000").rstrip("/")


def data_dir() -> Path:
    return Path(os.environ.get("OHARA_DATA_DIR", "/data"))


def docs_dir() -> Path:
    return data_dir() / "docs"


def static_dir() -> Path:
    return Path(os.environ.get("OHARA_STATIC_DIR", Path(__file__).parent / "static"))
