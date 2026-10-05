import io
import os
import tarfile

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from ohara import sessions, store

REPO = "acme/handbook"
URL = "https://docs.example.com"
os.environ["OHARA_URL"] = URL  # before any test imports ohara.main, which builds the OAuth routes from it


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("OHARA_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OHARA_URL", URL)
    sessions.sessions.clear()
    monkeypatch.setattr(sessions, "_loaded", False)
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
    def _configure(private=True):
        store.save(
            {
                "app": app_credentials,
                "installation_id": 42,
                "repo": {"full_name": REPO, "private": private, "default_branch": "main"},
            }
        )
        docs = data_dir / "docs"
        docs.mkdir(exist_ok=True)
        (docs / "README.md").write_text("# Home")
        (docs / "guide.md").write_text("# Guide")

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
