---
covers: [ntrossat/ohara:backend/ohara/docs.py, ntrossat/ohara:backend/ohara/freshness.py]
---

# Docs repository

The docs repository holds plain Markdown files, with no required config file. This page covers how Ohara turns them into a website.

## Layout

| Rule | Example |
|---|---|
| The folder tree is the menu | `guidelines/api.md` shows as "Api" under "Guidelines" |
| Pages are files ending in `.md`, in lowercase | `api.md`, not `api.MD` |
| Pages and folders are sorted by title | "Backend" comes before "Frontend" |
| A page's title is its front matter `title`, then its first `# ` heading, then its file name. Start the page with its heading: a `# ` line in a code block counts too | `# API guidelines` titles the page "API guidelines" |
| A folder's `index.md` or `README.md` is the folder's page, and its title names the folder. With both, `index.md` wins. The names are case-sensitive: `readme.md` is an ordinary page | `design/README.md` with `# Design` |
| A folder without an index page is named after the folder | `architecture/` shows as "Architecture" |
| The root `index.md` or `README.md` is the home page. With both, `index.md` wins | `README.md` at the root |
| Files and folders starting with `.` are hidden, and never served | `.github/` |
| Folders with no Markdown files are hidden | `assets/` with only images |
| Folders and pages listed in an optional `.oharaignore` at the root are left out of the menu, search, MCP listings, and stale pages. Their files still load where pages embed them, and their pages still open from a direct link. See below | `resources/` |
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

## Hide folders and pages

`.oharaignore` lists one pattern per line. Lines starting with `#` are comments.

| Pattern | Hides |
|---|---|
| `resources` or `resources/` | Every file or folder named `resources`, at any depth |
| `drafts/*.md` | Pages in the root `drafts/` folder. A pattern with `/` matches from the root |
| `*-old.md` | Every page whose name ends in `-old.md` |

Patterns use shell wildcards: `*` matches any characters, including `/`, and `?` one character. A leading or trailing `/` is ignored, and there is no `!` to bring a file back.

## Links and images

Link between pages with relative paths to the Markdown files, such as `[style guide](../design/style-guide.md)`. To link to a folder's page, link to its `README.md` or `index.md`: a link to the folder itself doesn't open. Images and other files work the same way: `![Logo](logo.svg)`. A video (`mp4`, `webm`, or `mov`) uses the image syntax too, `![Demo](demo.mp4)`, and plays once, muted, without controls.

Pages are Markdown with GitHub's extensions, such as tables and task lists. Headings get anchors, so `api.md#errors` links to a section. Code blocks are highlighted when they name their language, such as ` ```python `. HTML in a page is not rendered.

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
| `covers` | The code the page describes, as a list of `owner/repository:pattern`, or a single one. Patterns start at the repository root and are case-sensitive. `*` also matches across folders, so `src/billing/*` covers the whole folder, while `src/billing` only matches a file of that name |

A page is stale when:

- it was verified more than 180 days ago, or
- a push to the default branch of a covered repository changed files that match its patterns. The flag stays until the page itself changes, or for a year without a new matching push. Each page keeps its last 20 flags.

A page without `verified`, or with a value that isn't a date such as `2026-03-01`, never goes stale by age. Pushes to the docs repository itself never flag pages.

Covered repositories must have the GitHub App installed. See [Code repositories](code-repositories.md).

## Updates

A merge to the default branch updates the website within seconds: GitHub notifies Ohara, which downloads the new version and rebuilds the search index. Without a webhook, the website updates when Ohara restarts. Readers never see a half-updated site. Changing the repository's visibility on GitHub changes who can read the website.
