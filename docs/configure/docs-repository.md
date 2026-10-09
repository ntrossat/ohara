---
covers: [ntrossat/ohara:backend/ohara/docs.py, ntrossat/ohara:backend/ohara/freshness.py]
---

# Docs repository

The docs repository holds plain Markdown files, with no required config file. This page covers how Ohara turns them into a website.

## Layout

| Rule | Example |
|---|---|
| The folder tree is the menu | `guidelines/api.md` shows as "Api" under "Guidelines" |
| Pages and folders are sorted by title | "Backend" comes before "Frontend" |
| A page's title is its front matter `title`, then its first `# ` heading, then its file name | `# API guidelines` titles the page "API guidelines" |
| A folder's `index.md` or `README.md` is the folder's page, and its title names the folder. With both, `index.md` wins | `design/README.md` with `# Design` |
| A folder without an index page is named after the folder | `architecture/` shows as "Architecture" |
| The root `index.md` or `README.md` is the home page. With both, `index.md` wins | `README.md` at the root |
| Files and folders starting with `.` are hidden | `.github/` |
| Folders with no Markdown files are hidden | `assets/` with only images |
| Folders and pages listed in an optional `.oharaignore` at the root are left out of the menu, search, and MCP listings. Their files still load where pages embed them, and their pages still open from a direct link. One gitignore-style pattern per line; a pattern without `/` matches a name at any depth | `resources/` |
| `apps/` is reserved for docs synced from code repositories | `apps/api/` |

A suggested layout:

```text
README.md                 # home page: what this is and where to start
guidelines/               # engineering rules every assistant follows
  README.md
  api.md
  testing.md
architecture/             # how the systems fit together
design/                   # brand, style guide, UI kit
onboarding/               # for new hires
```

## Links and images

Link between pages with relative paths to the Markdown files, such as `[style guide](../design/style-guide.md)`. Images and other files work the same way: `![Logo](logo.svg)`. A video (`mp4`, `webm`, or `mov`) uses the image syntax too, `![Demo](demo.mp4)`, and plays once, muted, without controls.

## Freshness

Optional front matter tells Ohara who keeps a page up to date, when a human last checked it, and which code it describes.

```markdown
---
owner: ada
verified: 2026-03-01
covers: [acme/api:src/billing/*, acme/web:src/checkout/*]
---
```

| Field | Meaning |
|---|---|
| `owner` | Who keeps the page up to date |
| `verified` | The date a human last verified the page. Each proposal sets it to the day of the proposal, so merging the proposal verifies the page |
| `covers` | The code the page describes, as `owner/repository:pattern`. In patterns, `*` also matches across folders |

A page is stale when:

- it was verified more than 180 days ago, or
- a push to the default branch of a covered repository changed files that match its patterns. The flag stays until the page itself changes.

Covered repositories must have the GitHub App installed. See [Code repositories](code-repositories.md).

## Updates

A merge to the default branch updates the website within seconds: GitHub notifies Ohara, which downloads the new version and rebuilds the search index. Readers never see a half-updated site. Changing the repository's visibility on GitHub changes who can read the website.
