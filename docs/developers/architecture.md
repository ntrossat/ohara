---
order: 1
---

# Architecture

Ohara is one FastAPI process that serves the React website, a JSON API, and an MCP server, and talks to GitHub through one GitHub App. All state is in a data volume.

```
                 Browser                       MCP client
                    |                               |
                    v                               v
  +-------------------------- FastAPI ----------------------------+
  |  React app (static)   /api/*  (main.py)     /mcp (mcp_server) |
  |                         |                       |             |
  |   sessions.py  oauth.py  docs.py  freshness.py  appdocs.py    |
  |                         |                                     |
  |              db.py: /data/ohara.db     /data/docs (snapshot)  |
  +-------------------------------+-------------------------------+
                                  |  github.py (GitHub App)
                                  v
                    GitHub: docs repository, code repositories
                    (webhooks back to /api/github/webhook)
```

## Backend modules

| Module | Responsibility |
|---|---|
| `main.py` | Routes: setup, sign-in, docs API, the webhook, and the React app. Startup and background tasks |
| `github.py` | Every GitHub call: the app manifest, installation tokens, repository contents, Git trees and commits, pull requests, user sign-in, webhook signatures |
| `docs.py` | The snapshot: tarball extraction, navigation, page lookup, and the full-text search index |
| `freshness.py` | Owners, verified dates, `covers`, stale flags, and front matter edits |
| `codeowners.py` | Which docs files need review, from `CODEOWNERS` |
| `appdocs.py` | The sync of code repositories' docs into `apps/<repository>/` |
| `appconfig.py` | Reading and validating `.ohara.yml` |
| `mcp_server.py` | MCP tools and prompts, and the bearer-token guard on `/mcp` |
| `oauth.py` | The OAuth authorization server for MCP clients |
| `sessions.py` | Sign-in sessions and the 5-minute access check |
| `store.py` | Instance settings: app credentials and the docs repository |
| `db.py` | The SQLite database: JSON records by kind and key, with expiry, and the search table |
| `config.py` | `OHARA_URL`, its path, and the data directory |

## Frontend

| File | Screen |
|---|---|
| `App.tsx` | Reads `/api/status` and picks the screen |
| `Setup.tsx` | The setup page |
| `Gate.tsx` | Sign-in and "no access" screens |
| `Consent.tsx` | Approving an MCP client |
| `Docs.tsx` | The docs reader: menu, page, table of contents, edit link |
| `styles.css` | Design tokens and styles |

The server adds `<meta name="ohara-base">` to the page with the path of `OHARA_URL`, so the app works under a path.

## State

Nothing is kept in process memory apart from caches. `ohara.db` holds JSON records keyed by kind and key, each with an optional expiry:

| Kind | Content | Expires |
|---|---|---|
| `settings` | App credentials, installation, docs repository | Never |
| sessions | Signed-in users and their GitHub tokens | 30 days without use |
| OAuth records | MCP clients, pending sign-ins, token hashes | With the token |
| `check` | Cached access checks for GitHub bearer tokens | 5 minutes |
| `drift` | Stale flags from code changes, per page file | 1 year |
| `app` | The last sync of each code repository | Never |

The `pages` table is an SQLite FTS5 index of the snapshot, rebuilt on each update.

## Docs updates

1. A push to the docs repository's default branch sends a webhook. Ohara checks its signature with the app's webhook secret.
2. Ohara downloads the branch as a tarball with the installation token, extracts it next to the snapshot, and swaps the folders, so readers never see a half-written snapshot.
3. It rebuilds the search index.

The same runs on each start and on `repository` events, which also refresh the repository's visibility and default branch.

## Authentication

### Setup

1. Ohara posts a manifest to GitHub with the app's callback URLs, webhook, events, and permissions. The admin confirms on GitHub.
2. GitHub redirects to `/api/setup/callback`. Ohara checks the `state` it sent and exchanges the code for the app's credentials (ID, slug, client ID and secret, webhook secret, private key).
3. The admin installs the app. GitHub redirects to `/api/setup/installed`, and Ohara saves the installation.
4. The admin picks the docs repository. Then the setup routes lock.

### Website sign-in

GitHub OAuth with a random `state` in a short-lived cookie. The callback exchanges the code for a user token and a refresh token, creates a session, and sets the `ohara_session` cookie (HttpOnly, SameSite=Lax).

### MCP sign-in

Ohara is an OAuth authorization server. The client registers at `/register` and sends the user to `/authorize`. The user signs in with GitHub, then approves the client on the consent page. The consent cookie only exists in the browser that signed in, so a link from someone else can't silently hand them a token. The client gets Ohara tokens (`oha_`, 1 hour, refresh 30 days). Each grant is backed by its own session, so the GitHub token stays on the server.

### Access check

To check access, Ohara reads the docs repository with the user's own token. A user token only sees repositories both the user and the app can access, so success means the user can read the docs. The result is cached for 5 minutes. When a token expires, Ohara uses the refresh token once, then ends the session.

### Tokens

| Token | Belongs to | Used for |
|---|---|---|
| Installation token | The app | Downloading docs, reading repositories, committing synced docs, and opening, merging, and closing pull requests |
| User token | Each user | Checking what that user may read or write. Never leaves the server |
| `oha_` tokens | Each MCP grant | Calling `/mcp` |
| GitHub token as bearer | CI and headless agents | Calling `/mcp`, with the same checks as a user token |

## Proposals

`propose_change` maps each page path to a file, stamps `verified`, sorts the files (docs repository pages by `CODEOWNERS`, synced pages by their `source`), checks the caller's write access to each target repository, then commits on the right branches with the installation token and opens or updates the pull requests. See [API](api.md#mcp-server).

## App docs sync

`appdocs.sync` runs one sync at a time:

1. Read the code repository. A private one with a public docs repository syncs nothing.
2. Read `.ohara.yml` at the commit. Without it, nothing is synced.
3. List the code repository's files with the recursive trees API. A missing commit or a truncated list stops the sync, so missing files are never taken for deleted ones.
4. Lay out the files under `apps/<repository>/` and add `source` to each Markdown file.
5. Compare Git blob hashes with the docs repository's tree, upload the changed files, and delete the others.
6. Commit on the default branch, or on `ohara/sync-<repository>` with a pull request when the branch is protected.

On start, Ohara syncs every repository on the installation and removes `apps/` folders that belong to none of them.
