import pytest
from fastapi.testclient import TestClient

from ohara import docs, store


def test_robots_and_sitemap_public(client, configure, data_dir):
    configure(private=False)
    root = data_dir / "docs"
    (root / "guide.md").write_text("# Guide")
    docs.index(root)

    r = client.get("/robots.txt")
    assert r.status_code == 200
    assert "Allow: /" in r.text
    assert "Sitemap: https://docs.example.com/sitemap.xml" in r.text

    s = client.get("/sitemap.xml")
    assert s.status_code == 200
    assert s.headers["content-type"].startswith("application/xml")
    assert "<loc>https://docs.example.com/</loc>" in s.text or "<loc>https://docs.example.com</loc>" in s.text
    assert "<loc>https://docs.example.com/guide</loc>" in s.text


def test_robots_private_no_sitemap(client, configure):
    configure(private=True)
    r = client.get("/robots.txt")
    assert r.status_code == 200
    assert "Disallow: /" in r.text
    assert "Sitemap" not in r.text

    s = client.get("/sitemap.xml")
    assert s.status_code == 404
