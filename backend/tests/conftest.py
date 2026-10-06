import io
import os
import tarfile

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from ohara import docs, store

REPO = "acme/handbook"
URL = "https://docs.example.com"
os.environ["OHARA_URL"] = URL  # before any test imports ohara.main, which builds the OAuth routes from it


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("OHARA_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OHARA_URL", URL)
    return tmp_path


@pytest.fixture
def client():
    from ohara.main import app

    return TestClient(app, base_url="https://docs.example.com", follow_redirects=False)


@pytest.fixture(scope="session")
def pem():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()


@pytest.fixture
def app_credentials(pem):
    return {
        "id": 1,
        "slug": "ohara-docs",
        "client_id": "Iv1.abc",
        "client_secret": "shh",
        "webhook_secret": "hook-secret",
        "pem": pem,
    }


@pytest.fixture
def configure(app_credentials, data_dir):
    def index_docs():
        docs.index(data_dir / "docs")

    def _configure(private=True):
        store.save(
            {
                "app": app_credentials,
                "installation_id": 42,
                "repo": {"full_name": REPO, "private": private, "default_branch": "main"},
            }
        )
        root = data_dir / "docs"
        root.mkdir(exist_ok=True)
        (root / "README.md").write_text("# Home")
        (root / "guide.md").write_text("# Guide")
        index_docs()

    return _configure


def tarball(files, links=()):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, text in files.items():
            data = text.encode()
            info = tarfile.TarInfo(f"owner-repo-abc123/{name}")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        for name, target in links:
            info = tarfile.TarInfo(f"owner-repo-abc123/{name}")
            info.type = tarfile.SYMTYPE
            info.linkname = target
            tar.addfile(info)
    return buf.getvalue()


@pytest.fixture
def mcp(monkeypatch):
    from ohara import main

    async def no_sync():
        pass

    monkeypatch.setattr(main, "safe_sync", no_sync)
    with TestClient(main.app, base_url="https://docs.example.com", follow_redirects=False) as client:
        yield client


@pytest.fixture
def synced(monkeypatch):
    from ohara import main

    calls = []

    async def fake_sync():
        calls.append(True)

    monkeypatch.setattr(main, "safe_sync", fake_sync)
    return calls
