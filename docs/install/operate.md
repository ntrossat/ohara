---
covers: [ntrossat/ohara:Dockerfile, ntrossat/ohara:docker-compose.yml, ntrossat/ohara:.github/workflows/*, ntrossat/ohara:backend/ohara/db.py, ntrossat/ohara:backend/ohara/store.py]
---

# Operate

How to keep Ohara running: data, backups, updates, continuous deployment, and fixes for common problems.

## Data

All state lives in the data volume, mounted at `/data`. Nothing is kept in memory apart from caches, so the container can restart at any time.

| Path | Content |
|---|---|
| `ohara.db` | SQLite database: GitHub App credentials, the chosen docs repository, sign-in sessions, MCP clients and token hashes, cached access checks, stale flags, the last sync of each code repository, and the search index |
| `docs/` | The latest snapshot of the docs repository |

`ohara.db` holds the app's private key and users' GitHub tokens. Only the server reads it. Treat the volume as a secret.

## Back up and restore

Back up the volume. Stop the container first, or copy the database with SQLite's backup command, so the copy is consistent:

```bash
docker compose exec ohara python -c "import sqlite3; sqlite3.connect('/data/ohara.db').backup(sqlite3.connect('/data/backup.db'))"
```

The docs themselves are in GitHub, so a lost volume costs the setup, the sign-ins, and the stale flags from code changes. To start again, delete the old GitHub App on GitHub, since setup creates a new one with the same name, then open the setup page.

`docker compose down -v` deletes the volume and resets Ohara to the setup page.

## Update Ohara

```bash
git pull
docker compose up -d --build
```

The data volume is kept: settings, sessions, MCP sign-ins, and docs survive the update. On each start, Ohara downloads the docs again and checks every code repository's sync.

Instances created before some features need a change in the GitHub App's settings:

| Feature | Change |
|---|---|
| Proposals | Grant **Contents** and **Pull requests** write permissions, then accept them on the installation |

## Images

Each push to `main` and each `v*` tag that passes CI publishes an image to the GitHub Container Registry, `ghcr.io/<owner>/ohara`:

| Tag | Points to |
|---|---|
| `main` | The latest commit on `main` |
| `sha-<commit>` | One commit, by its first 12 characters |
| `<version>`, `<major>.<minor>`, `latest` | A `v*` release tag |

The image name follows the repository, `ghcr.io/<owner>/<repository>`, so a fork publishes its own.

The repository's `docker-compose.yml` builds the image from source. A Compose file that runs the published image is on the roadmap.

## Continuous deployment

The CD workflow (`.github/workflows/cd.yml`) can deploy each push to `main` that passes CI. It keeps your hosting details out of the code: set them in the repository's **Settings › Secrets and variables › Actions**.

| Setting | Kind | Content |
|---|---|---|
| `DEPLOY_COMMAND` | Variable | A shell script that deploys. It runs in a checkout of the commit, with `$IMAGE` set to the published image |
| `DEPLOY_TOKEN` | Secret | The credential the script needs, available as `$DEPLOY_TOKEN` |

Without `DEPLOY_COMMAND`, the workflow only publishes the image. For example, a host with a deploy hook:

```bash
curl -fsS -X POST "https://deploy.example.com/hooks/ohara?image=$IMAGE" -H "Authorization: Bearer $DEPLOY_TOKEN"
```

## Switch to another docs repository

The repository is chosen once, at setup. To point Ohara to another one:

1. Delete the GitHub App in GitHub, under **Settings › Developer settings › GitHub Apps** (for an organization, its settings).
2. Remove the data volume: `docker compose down -v`. This also signs everyone out and disconnects every coding assistant.
3. Start Ohara again and follow the setup.

## Uninstall

1. Stop Ohara and remove its data: `docker compose down -v --rmi local`.
2. Delete the GitHub App on GitHub, under **Settings › Developer settings › GitHub Apps** (for an organization, its settings). This also removes it from every repository.
3. In each project set up with `/ohara:init`, remove the `ohara` server from `.mcp.json`, the "Ohara instructions" section from `CLAUDE.md`, the Ohara tools from `.claude/settings.json`, and `.ohara.yml`.

The docs repository and its pull requests stay on GitHub.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| The website doesn't update after a merge | GitHub can't reach the webhook. Check that `OHARA_URL` is public, and look at **Recent Deliveries** in the app's settings on GitHub. Restarting Ohara also updates the docs |
| The website shows old docs, and the logs say `sync failed` | Ohara can't read the docs repository: the app was removed from it, or the repository was renamed or deleted. Ohara keeps serving the last copy. Add the app back to the repository, or start over |
| Setup stops while it downloads the docs | Choosing the docs repository downloads it and every code repository's docs in the same request. Raise the reverse proxy's timeout, or install the app on fewer code repositories at first |
| A coding assistant gets "Sign in required" on a public docs repository | Reading needs no sign-in, so the assistant never signs in. Send a GitHub token as `Authorization: Bearer` to propose changes |
| The API or MCP server answers "Ohara is not set up yet" | Setup didn't finish. Open `OHARA_URL` and complete it |
| Coding assistants can't sign in | MCP sign-in needs an `https://` address or `localhost`. Otherwise, send a GitHub token as `Authorization: Bearer` |
| A proposal fails with a permissions error | The app lacks write permissions. Grant **Contents** and **Pull requests** write in the app's settings, then accept them on the installation |
| A code repository's docs don't appear under `apps/` | The repository needs a `.ohara.yml`, the app must be installed on it, and a private code repository is never synced into a public docs repository. Ask a coding assistant to call `check_repository` for the reason |
| Someone still reads the docs after losing access | Access is checked again every 5 minutes, so it ends within 5 minutes |

Logs go to the container's output, at the `INFO` level: `docker compose logs -f`.
