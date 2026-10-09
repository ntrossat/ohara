---
covers: [ntrossat/ohara:backend/ohara/main.py, ntrossat/ohara:backend/ohara/mcp_server.py]
verified: 2026-10-09
---

# API

All routes are under `OHARA_URL`, including its path, apart from OAuth discovery for MCP clients, which stays at the root of the host (see [Serve Ohara under a path](../install/README.md#serve-ohara-under-a-path)).

Before setup finishes, the docs routes and `/mcp` answer `503` with "Ohara is not set up yet".

## HTTP routes

| Route | Access | Purpose |
|---|---|---|
| `GET /api/status` | Everyone | Setup state, docs repository, branch, visibility, the signed-in user, and whether they can read |
| `GET /api/nav` | Readers | The menu, built from the folder tree |
| `GET /api/page?path=` | Readers | A page's title, file, Markdown, and for a synced page its `source` (repository, path, edit URL) |
| `GET /api/files/*` | Readers | Images and other files from the docs repository, with a strict Content-Security-Policy |
| `GET /api/setup/manifest?org=` | Before setup | The GitHub App manifest and the form action. `org` creates the app under an organization |
| `GET /api/setup/callback` | Before setup | GitHub's return after creating the app |
| `GET /api/setup/installed` | Once the app exists | GitHub's return after an install. Picks the docs repository when the installation has only one. Redirects to the website once set up |
| `GET /api/setup/repositories` | Before setup | The installation's repositories |
| `POST /api/setup/repository` | Before setup | Choose the docs repository |
| `GET /api/auth/login` | Everyone | Start GitHub sign-in |
| `GET /api/auth/callback` | Everyone | GitHub's return after sign-in |
| `GET`, `POST /api/auth/consent` | The signed-in browser | Details and answer for an MCP client's approval |
| `POST /api/auth/logout` | Everyone | End the session |
| `POST /api/github/webhook` | GitHub, signed | Events, below |
| `GET`, `POST`, `DELETE /mcp` | Readers | The MCP server |
| `/.well-known/*`, `/register`, `/authorize`, `/token`, `/revoke` | MCP clients | OAuth for MCP clients |
| `/setup`, `/oauth/consent`, any other path | Everyone | The React app, which picks the screen |

"Readers" means everyone for a public docs repository, and signed-in users who can read it for a private one. Others get `401` (not signed in) or `403` (no access).

## Webhook events

| Event | From | Ohara |
|---|---|---|
| `push` to the default branch | Docs repository | Updates the snapshot |
| `push` to the default branch | Code repository | Syncs its docs if they or `.ohara.yml` changed, then flags the pages that cover the changed files |
| `repository` | Docs repository | Updates the snapshot, visibility, and default branch, and syncs every code repository again |
| `installation_repositories` | Ohara's installation | Syncs added repositories, and removes the folders of removed ones |

Other events and other installations are ignored. Each delivery is checked against the webhook secret: a bad signature gets `401`.

## MCP server

Streamable HTTP, stateless, at `/mcp`. Callers send `Authorization: Bearer` with an `oha_` token or a GitHub token. For a public docs repository, reading needs no token, but an invalid or expired token still gets `401`. A signed-in user who can't read a private docs repository gets `403`. A `401` carries a `WWW-Authenticate: Bearer resource_metadata="..."` header that points MCP clients to Ohara's OAuth metadata.

### Tools

| Tool | Arguments | Returns |
|---|---|---|
| `list_pages` | None | Each page's `path`, `title` with its folders, and `source` for synced pages |
| `search` | `query` | Up to 20 pages containing every word: `path`, `title`, `snippet`, `stale` reasons, and `source` |
| `read_page` | `path` (empty for the home page) | Title, Markdown, owner, verified date, covers, stale reasons, `source` |
| `stale_pages` | None | Stale pages: `path`, `title`, `owner`, `verified`, `covers`, and the `stale` reasons |
| `check_repository` | `repository` (`owner/name`) | `connected`, `reason`, `settings_url`, synced `docs` paths, `synced_folder` |
| `propose_change` | `title`, `description`, `pages` (`path`, `markdown`), and optionally `project` and `branch`, or `pull_request` (a URL or number) | The pull request URL |
| `import_docs` | None | The `ingest` prompt's steps, for clients without prompts, such as chat apps |

`check_repository` and `propose_change` need a signed-in caller, even for a public docs repository: there, a call to either without a token gets `401`, so the client signs in and calls again. `propose_change` also needs write access to the docs repository. It picks the docs branch in this order:

1. `project` and `branch` both set: the `<project>/<branch>` branch.
2. `pull_request` set: the branch of that pull request, if it is open and not from a fork. Otherwise, a new branch.
3. Neither: a new `ohara/<slug>-<random>` branch.

Search uses SQLite FTS5 with English stemming, and weighs titles ten times more than the text. Pages hidden by `.oharaignore` are left out of `list_pages`, `search`, and `stale_pages`, but `read_page` still returns them.

### Prompts

| Prompt | Command in Claude Code |
|---|---|
| `init` | `/ohara:init` |
| `update` | `/ohara:update` |
| `review` | `/ohara:review` |
| `ingest` | `/ohara:ingest` |

Each prompt is a set of instructions for the assistant, filled with the instance's address and docs repository. See [Coding assistants](../use/coding-assistants.md#commands).
