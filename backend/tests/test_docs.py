from ohara import docs
from tests.conftest import tarball


def write(root, rel, text):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_title_from_front_matter_then_heading_then_filename(tmp_path):
    write(tmp_path, "a.md", "---\ntitle: From meta\n---\n# Heading\n")
    write(tmp_path, "b.md", "Intro\n\n# From heading\n")
    write(tmp_path, "getting-started.md", "No heading here")
    titles = [n["title"] for n in docs.build_nav(tmp_path)]
    assert titles == ["From heading", "From meta", "Getting started"]


def test_nav_mirrors_folders_and_uses_index_pages(tmp_path):
    write(tmp_path, "README.md", "# Home")
    write(tmp_path, "guidelines/index.md", "# Guidelines")
    write(tmp_path, "guidelines/python.md", "# Python")
    write(tmp_path, "architecture/overview.md", "# Overview")
    write(tmp_path, ".github/template.md", "# Hidden")
    write(tmp_path, "notes.txt", "not markdown")

    nav = docs.build_nav(tmp_path)

    assert nav == [
        {
            "title": "Architecture",
            "path": None,
            "folder": "architecture",
            "children": [{"title": "Overview", "path": "architecture/overview", "children": []}],
        },
        {
            "title": "Guidelines",
            "path": "guidelines",
            "folder": "guidelines",
            "children": [{"title": "Python", "path": "guidelines/python", "children": []}],
        },
    ]


def test_front_matter_order_wins_over_title(tmp_path):
    write(tmp_path, "a.md", "# Alpha")
    write(tmp_path, "z.md", "---\norder: 1\n---\n# Zulu")
    assert [n["title"] for n in docs.build_nav(tmp_path)] == ["Zulu", "Alpha"]


def test_read_page_strips_front_matter_and_finds_index(tmp_path):
    write(tmp_path, "README.md", "---\norder: 1\n---\n# Home\nWelcome")
    write(tmp_path, "guides/index.md", "# Guides")
    assert docs.read_page(tmp_path, "") == {
        "title": "Home", "file": "README.md", "markdown": "# Home\nWelcome", "meta": {"order": 1}
    }
    assert docs.read_page(tmp_path, "guides")["file"] == "guides/index.md"
    assert docs.read_page(tmp_path, "missing") is None


def test_paths_cannot_escape_docs_dir(tmp_path):
    root = tmp_path / "docs"
    write(root, "page.md", "# Page")
    write(tmp_path, "secret.md", "# Secret")
    assert docs.read_page(root, "../secret") is None
    assert docs.resolve_file(root, "../secret.md") is None
    assert docs.resolve_file(root, "page.md") == (root / "page.md").resolve()


def test_bad_front_matter_is_treated_as_text(tmp_path):
    write(tmp_path, "a.md", "---\n: [unclosed\n---\n# Title")
    assert docs.read_page(tmp_path, "a")["title"] == "Title"


def test_extract_strips_prefix_and_replaces_previous_snapshot(tmp_path):
    root = tmp_path / "docs"
    write(root, "old.md", "# Old")
    docs.extract(tarball({"README.md": "# Home", "a/b.md": "# B"}), root)
    assert (root / "README.md").read_text() == "# Home"
    assert (root / "a/b.md").read_text() == "# B"
    assert not (root / "old.md").exists()


def test_extract_skips_links_and_escaping_paths(tmp_path):
    root = tmp_path / "docs"
    docs.extract(tarball({"ok.md": "# Ok", "../../evil.md": "x"}, links=[("link.md", "/etc/passwd")]), root)
    assert (root / "ok.md").exists()
    assert not (root / "link.md").exists()
    assert not (tmp_path / "evil.md").exists()
