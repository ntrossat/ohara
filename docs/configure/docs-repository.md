---
order: 1
---

# Docs repository

The docs repository holds plain Markdown files, with no config file. This page covers how Ohara turns them into a website.

## Layout

| Rule | Example |
|---|---|
| The folder tree is the menu | `guidelines/api.md` shows as "Api" under "Guidelines" |
| A page's title is its front matter `title`, then its first `# ` heading, then its file name | `# API guidelines` titles the page "API guidelines" |
| A folder's `index.md` or `README.md` is the folder's page, and its title names the folder. With both, `index.md` wins | `design/README.md` with `# Design` |
| A folder without an index page is named after the folder | `architecture/` shows as "Architecture" |
| The root `README.md` is the home page | |
| Files and folders starting with `.` are hidden | `.github/` |
| Folders with no Markdown files are hidden | `assets/` with only images |
| `apps/` is reserved for docs synced from code repositories | `apps/api/` |

A suggested layout:

```
README.md                 # home page: what this is and where to start
guidelines/               # engineering rules every assistant follows
  README.md
  api.md
  testing.md
architecture/             # how the systems fit together
design/                   # brand, style guide, UI kit
onboarding/               # for new hires
CODEOWNERS                # folders that always need a review
```

## Order

Pages are sorted by title. To choose the order, add `order` to the front matter. Lower numbers come first, and pages with an order come before pages without one. A folder takes the order of its index page.

```markdown
---
order: 1
title: Getting started
---

# Getting started
```

## Links and images

Link between pages with relative paths to the Markdown files, such as `[style guide](../design/style-guide.md)`. Images and other files work the same way: `![Logo](logo.svg)`.

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

## Review rules

A `CODEOWNERS` file in the docs repository, in `.github/`, at the root, or in `docs/`, names the folders that always need a human review. Pages without a code owner merge with the code change that updated them. See [Merge docs with the code](code-repositories.md#merge-docs-with-the-code).

## Updates

A merge to the default branch updates the website within seconds: GitHub notifies Ohara, which downloads the new version and rebuilds the search index. Readers never see a half-updated site. Changing the repository's visibility on GitHub changes who can read the website.
