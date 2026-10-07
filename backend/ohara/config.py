"""All environment configuration: the public address, and where the data and the React app live.
No other module reads the environment."""

import os
from pathlib import Path
from urllib.parse import urlparse


def base_url() -> str:
    return os.environ.get("OHARA_URL", "http://localhost:8000").rstrip("/")


def base_path() -> str:
    """The path Ohara is served under, such as "/docs", or "" at the root of its host."""
    return urlparse(base_url()).path.rstrip("/")


def data_dir() -> Path:
    """The data volume: the docs snapshot and the database."""
    return Path(os.environ.get("OHARA_DATA_DIR", "/data"))


def docs_dir() -> Path:
    return data_dir() / "docs"


def static_dir() -> Path:
    """The built React app, copied next to the package in the Docker image."""
    return Path(os.environ.get("OHARA_STATIC_DIR", Path(__file__).parent / "static"))
