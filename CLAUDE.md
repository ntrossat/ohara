# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Status

Ohara (one central place for all enterprise knowledge) has a first version of the docs website. `README.md` is the source of truth for scope.

## Commands

- Backend tests: `cd backend && uv run pytest`
- Backend dev server: `cd backend && OHARA_DATA_DIR=.data uv run uvicorn ohara.main:app --reload`
- Frontend dev server: `cd frontend && npm run dev` (proxies `/api` to port 8000)
- Frontend build and type check: `cd frontend && npm run build`
- Full app: `make dev` (`docker compose up --build --watch`, rebuilds on code changes, reads `OHARA_URL` from `.env`)
- CI and CD: `.github/workflows/ci.yml` runs the tests on pull requests, `main`, and `v*` tags; `cd.yml` publishes the image to `ghcr.io/<owner>/ohara` once CI passes on `main` (tags `main`, `sha-<commit>`) or on a `v*` tag (the version and `latest`), then runs the repository variable `DEPLOY_COMMAND`, if set, with `$IMAGE` and the `DEPLOY_TOKEN` secret. Hosting details live only in those settings.
- Fresh install: `make init` (removes the container, image, and data volume, then runs `make dev`; delete the old GitHub App by hand)

## Layout

- `backend/ohara/`: FastAPI app. `main.py` holds routes, `github.py` the GitHub App calls, `docs.py` the docs snapshot and navigation, `sessions.py` sign-in and access checks, `store.py` the instance settings, `db.py` the SQLite database in the data volume (all state: settings, sessions, OAuth grants, the full-text search index), `mcp_server.py` the MCP server at `/mcp`, `oauth.py` the OAuth sign-in for MCP clients, `freshness.py` page owners, verified dates, and code-change flags, `appdocs.py` the sync of code repositories' docs into `apps/<repo>/` of the docs snapshot, `appconfig.py` their `.ohara.yml`, which a repository needs to be synced, `config.py` the environment configuration (`OHARA_URL`, its base path, the data directory). MCP tools: `list_pages`, `read_page`, `search`, `stale_pages`, `check_repository`, `propose_change`, `import_docs` (the `ingest` steps, for chat apps). MCP prompts (`/ohara:<name>` in Claude Code): `init` sets up a project (checks the GitHub App is installed on its repository and opens the installation settings if not, `.mcp.json`, a `CLAUDE.md` section with the guidelines, docs, and workflow, and read permissions for the Ohara tools); `update` proposes doc updates from the project's latest code changes; `review` reviews the project against the guidelines and docs; `ingest` imports existing docs from other tools as pull requests.
- `frontend/src/`: React app. `Setup.tsx` is the setup page, `Gate.tsx` the sign-in screen, `Consent.tsx` the page where a user approves an MCP client, `Docs.tsx` the docs reader, `styles.css` the design tokens and styles. The UI follows the brand guidelines, style guide, and UI kit in the `design/` folder of the project's docs repository.
- The Docker image builds the frontend and serves it from FastAPI. All state lives in the `/data` volume: the docs snapshot and `ohara.db`. Nothing is kept in process memory, apart from caches.

## Product

Ohara is an open-source enterprise documentation manager. AI keeps documentation and engineering guidelines up to date, and a human approves every change.

- **Docs as code:** documentation lives in a configurable GitHub repository. Every change goes through a pull request. Code repositories can keep their own docs and opt in with a `.ohara.yml` listing them (`/ohara:init` writes it with `docs`): Ohara syncs them one way into `apps/<repo>/` of its docs snapshot on each push, without committing them to the docs repository, and never from a private code repository when the docs repository is public. The docs changes of a code branch go to one docs pull request, which a human reviews and merges.
- **Access layers:** an HTML UI for reading and configuration, and an MCP server for AI agents and coding assistants.
- **Roadmap:** an AI chat over the docs, and a Compose file that runs the published image instead of building it.
- **Access control:** the website uses GitHub SSO and mirrors the docs repository's access rights. A public repository means a public website. A private repository requires sign-in, and only users with access to the repository can read the website.
- **Ingestion:** a Claude agent imports existing docs through MCP (Jira, Confluence, GitHub, Google Drive). It submits them as PRs, with a review for security and prompt injection.
- **Planned commands:**
  - `/ohara:init` configures the active project (built).
  - `/ohara:update` updates the docs from the active project's code changes (built).
  - `/ohara:ingest` pulls existing docs into Ohara (built).
  - `/ohara:review` reviews the active project against the guidelines (built).
- **Workflow:** architects define guidelines, the coding assistant proposes an architecture for each new feature, architects and engineers review it, the assistant builds from the approved plan and updates the docs, and engineers review the result.

## Stack

- Frontend: React with Vite.
- Backend: Python with FastAPI.
- Deployment: Docker Compose, so anyone can self-host on any platform. The address is configurable, and can include a path (such as `/docs`): the backend serves everything under it, and the frontend reads the path from a meta tag the server adds to the page.
- GitHub integration: one GitHub App, created through the manifest flow from Ohara's setup page, then installed on the docs repository. It handles sign-in, access to the docs repository, merge events that trigger rebuilds, pushes to code repositories (when installed on them) that flag stale pages, and the pull requests that MCP clients propose. The app opens those pull requests, so the proposing user can still review and approve them; only users with write access to the repository can propose.
- Access checks: for a private docs repository, the backend re-checks each user's repository access with GitHub every 5 minutes. A user whose access is removed loses the website within 5 minutes. The MCP server applies the same rule. MCP clients sign in through OAuth: Ohara is the authorization server, GitHub sign-in proves the user, the user approves the client on Ohara's consent page, and Ohara issues its own short-lived `oha_` tokens while the GitHub token stays on the server. CI and headless agents can send a GitHub token as `Authorization: Bearer` instead.
- Docs repository format: plain Markdown files with no required config file. An optional `.oharaignore` at the root hides folders and pages from the menu, search, and MCP listings, while their files still load. The folder tree becomes the site menu, and each page's first heading is its title. Pages are sorted by title. Optional front matter tracks freshness: `owner`, `verified` (set on every proposed change, so merging verifies the page), and `covers` (`repository:pattern` entries; a push to a covered repository's default branch flags the page until the page changes). Pages unverified for 180 days are stale.
- Configuration: the domain is the only environment variable in Docker Compose. On first launch, a setup page creates the GitHub App, the admin installs it on the docs repository and the code repositories, then picks the docs repository in Ohara (picked automatically when the app has only one). Settings are saved in a Docker volume.
- First version: the setup page, GitHub sign-in with access that mirrors the docs repository, docs rendering, a rebuild on each merge, and an MCP server that reads pages and proposes changes as pull requests. The AI chat comes later.

## Open source

Ohara is an open-source project. Never commit anything specific to one company, deployment, or person: no hosting provider, domain, credentials, or names of repositories other than the project's own. Make it configurable instead.

## Repositories

- This repo holds the application code, including the HTML website, and Ohara's own product docs in `docs/` (for executives, admins, and developers). `.ohara.yml` syncs them into `apps/ohara/` of the website on each push to `main`. Never add other documentation here.
- Guidelines and all other documentation live in a separate, configurable docs repository. Each company points Ohara to its own repository. Never hard-code a docs repository name.
- A merge to `main` in the docs repository triggers a site rebuild here.

## Conventions

- Never work on `main`. Create a branch before the first change, and merge it into `main` through a pull request.
- Use Conventional Commits (`docs:`, `chore:`, …).
- Keep `README.md` focused on principles and features. Implementation details, architecture diagrams, and tech stack tables were removed from it on purpose.

## Ohara instructions

Ohara, reached through the `ohara` MCP server in `.mcp.json`, is the source of truth for documentation and engineering guidelines. This project's own docs live in `docs/` and Ohara syncs them: update them in the same change as the code. Every other page lives in Ohara: propose changes to it, never add it to this repository.

Guidelines:

- `design`: index of the design pages, the `tokens.css` design tokens, the logo files, and the UI mockups.
- `design/brand`: name, logo, colors, typefaces, and voice.
- `design/style-guide`: design tokens (color, type, spacing, shapes, layout, motion), accessibility, and copy rules.
- `design/ui-kit`: component and screen specs for the website.

Project docs, in `docs/` (synced to `apps/ohara/`):

- `docs/README.md`: what Ohara is and who it helps, for executives.
- `docs/concepts.md`: how Ohara works, and a glossary.
- `docs/install/`: installing, setup, HTTPS, paths, and operating (data, updates, CD, troubleshooting).
- `docs/configure/`: the docs repository layout, code repositories (covers, docs pull requests from a code branch, `.ohara.yml` sync), and access.
- `docs/use/`: coding assistants, the `/ohara:*` commands, chat apps, and the team workflow.
- `docs/developers/`: architecture, API, development, and customizing.

Workflow:

- Before planning a change, read the guidelines and docs that apply, and search Ohara for anything else relevant. Say when a page you rely on is stale.
- Propose an architecture that follows the guidelines, and name the guidelines it relies on.
- After the change, check it against the guidelines and fix what does not follow them.
- Then update `docs/` in the same change, and propose updates to every other page the change affects in one `propose_change`, with the project `ohara` and the active git branch, so each code branch gets a single pull request to review. Put the docs pull request links in the code pull request's description.
