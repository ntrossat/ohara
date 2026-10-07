---
order: 1
covers: [ntrossat/ohara:backend/ohara/*, ntrossat/ohara:frontend/src/*]
---

# Architecture

Ohara is one FastAPI process that serves the React website, a JSON API, and an MCP server, and talks to GitHub through one GitHub App. All state is in a data volume.

```text
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
| `github.py` | Every GitHub call, through one shared client with a timeout, keeping only the fields Ohara uses: the app manifest, installation tokens, repository contents, Git trees and commits, pull requests, user sign-in, webhook signatures |
| `docs.py` | The snapshot: tarball extraction, navigation, page lookup, and the pages it puts in the search index |
| `freshness.py` | Owners, verified dates, `covers`, stale flags, and front matter edits |
| `appdocs.py` | The sync of code repositories' docs into `apps/<repository>/` |
| `appconfig.py` | Reading and validating `.ohara.yml` |
| `mcp_server.py` | MCP tools and prompts, and the bearer-token guard on `/mcp` |
| `oauth.py` | The OAuth authorization server for MCP clients |
| `sessions.py` | Sign-in sessions and the 5-minute access check |
| `store.py` | Instance settings: app credentials and the docs repository |
| `db.py` | The SQLite database: JSON records by kind and key, with expiry, and the search table and its queries. No other module runs SQL |
| `config.py` | All environment configuration: `OHARA_URL`, its path, the data directory, and the React app directory |

## Frontend

| File | Screen |
|---|---|
| `main.tsx` | Loads the fonts and styles, and mounts the app under the path from `<meta name="ohara-base">` |
| `App.tsx` | Reads `/api/status` and picks the screen |
| `api.ts` | API types, the base path, and `get`, which reloads the page on 401 or 403 so the sign-in screen shows |
| `Setup.tsx` | The setup page |
| `Gate.tsx` | Sign-in and "no access" screens, and `Unreachable` when the server doesn't answer |
| `Consent.tsx` | Approving an MCP client |
| `Docs.tsx` | The docs reader: menu with a filter, breadcrumbs, page, table of contents, previous and next links, edit link, code blocks with a copy button, and sign out |
| `nav.ts` | The reading order for previous and next links, and the breadcrumb trail |
| `links.ts` | Resolves relative Markdown links to site routes and file URLs |
| `Mark.tsx` | The Ohara logo |
| `styles.css` | Design tokens and styles |

The server adds `<meta name="ohara-base">` to the page with the path of `OHARA_URL`, so the app works under a path.

## State

Nothing is kept in process memory apart from caches. `ohara.db` holds JSON records keyed by kind and key, each with an optional expiry:

| Kind | Content | Expires |
|---|---|---|
| `settings` | App credentials, installation, docs repository | Never |
| `session` | Signed-in users and their GitHub tokens | 30 days without use |
| `client` | Registered MCP clients, the newest 1,000 kept | Never |
| `pending`, `code`, `consent` | Pending MCP sign-ins, authorization codes, and consent requests | 10 minutes |
| `access` | Hashes of `oha_` access tokens | 1 hour |
| `refresh` | Hashes of refresh tokens | 30 days |
| `setup` | The `state` of a pending app creation | 10 minutes, or once used |
| `check` | Cached access checks for GitHub bearer tokens | 5 minutes |
| `drift` | Stale flags from code changes, per page file | 1 year |
| `app` | The last sync of each code repository | Never |

The `pages` table is an SQLite FTS5 index of the snapshot, rebuilt on each update.

Earlier versions saved `settings.json`, `sessions.json`, and `oauth.json`. On first start, Ohara imports them into `ohara.db` and renames them `*.json.imported`.

## Docs updates

1. A push to the docs repository's default branch sends a webhook. Ohara checks its signature with the app's webhook secret.
2. Ohara downloads the branch as a tarball with the installation token, extracts it next to the snapshot, and swaps the folders, so readers never see a half-written snapshot.
3. It rebuilds the search index.

The same runs on each start and on `repository` events, which also refresh the repository's visibility and default branch.

## Authentication

### Setup

1. Ohara posts a manifest to GitHub with the app's callback URLs, webhook, events, and permissions. The admin confirms on GitHub.
2. GitHub redirects to `/api/setup/callback`. Ohara checks the `state` it sent, which works once and for 10 minutes, and exchanges the code for the app's credentials (ID, slug, client ID and secret, webhook secret, private key).
3. The admin installs the app. GitHub redirects to `/api/setup/installed`, and Ohara saves the installation.
4. The admin picks the docs repository. Then the setup routes lock.

### Website sign-in

GitHub OAuth with a random `state` in a short-lived cookie. The callback exchanges the code for a user token and a refresh token, creates a session, and sets the `ohara_session` cookie. Every Ohara cookie is HttpOnly and SameSite=Lax, and Secure when `OHARA_URL` starts with `https://`. Each use renews the cookie, so a session ends after 30 days without use.

### MCP sign-in

Ohara is an OAuth authorization server. The client registers at `/register` and sends the user to `/authorize`. The user signs in with GitHub, then approves the client on the consent page. The consent cookie only exists in the browser that signed in, so a link from someone else can't silently hand them a token. The client gets Ohara tokens (`oha_`, 1 hour, refresh 30 days). Each grant is backed by its own session, so the GitHub token stays on the server. Ohara stores only hashes of its tokens, and keeps the newest 1,000 registered clients, since registration is open.

OAuth needs `OHARA_URL` to start with `https://` or to use a loopback address: `localhost`, `127.0.0.1`, or `[::1]`. Otherwise Ohara logs a warning, disables MCP sign-in, and only GitHub tokens work.

### Access check

To check access, Ohara reads the docs repository with the user's own token. A user token only sees repositories both the user and the app can access, so success means the user can read the docs. The result is cached for 5 minutes. When a token expires, Ohara uses the refresh token once, then ends the session.

### Tokens

| Token | Belongs to | Used for |
|---|---|---|
| Installation token | The app | Downloading docs, reading repositories, committing synced docs, and opening pull requests |
| User token | Each user | Checking what that user may read or write. Never leaves the server |
| `oha_` tokens | Each MCP grant | Calling `/mcp` |
| GitHub token as bearer | CI and headless agents | Calling `/mcp`, with the same checks as a user token |

## Proposals

`propose_change` maps each page path to a file, stamps `verified`, sorts the files (docs repository pages, and synced pages by their `source`), checks the caller's write access to each target repository, then commits on the right branches with the installation token and opens or updates the pull requests. See [API](api.md#mcp-server).

| Branch | Holds |
|---|---|
| `<project>/<branch>` | Docs repository pages proposed from that code branch |
| `ohara/<slug>-<random>` | Every docs repository page, when no project and branch are given |
| `<project>/<branch>` or `ohara/<slug>-<random>` on a code repository | Synced pages of that repository, at their source path |

Characters other than letters, digits, `_` and `-` in branch names become `-`. When a branch has an open pull request, the commits go to it with a comment that holds the title and description. A branch left from a closed pull request is reset to the default branch first, so it holds only the new change.

## Freshness flags

When a code repository pushes to its default branch, the webhook lists the changed files with GitHub's compare API (or the push's commits, for a new branch), syncs the repository's docs when they changed, and matches the files against each page's `covers`. Each match records a flag with the date, the files, and a compare link, up to 20 per page. A flag holds a hash of the page's file: when the page changes, the flags are dropped.

## App docs sync

`appdocs.sync` runs one sync at a time:

1. Read the code repository. A private one with a public docs repository syncs nothing.
2. Read `.ohara.yml` at the commit. Without it, nothing is synced.
3. List the code repository's files with the recursive trees API. A missing commit or a truncated list stops the sync, so missing files are never taken for deleted ones.
4. Lay out the files under `apps/<repository>/` and add `source` to each Markdown file.
5. Compare Git blob hashes with the docs repository's tree, upload the changed files, and delete the others.
6. Commit on the default branch, or on `ohara/sync-<repository>` with a pull request when the branch is protected.

On start, Ohara syncs every repository on the installation and removes `apps/` folders that belong to none of them.
