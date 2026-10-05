# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Status

Ohara (one central place for all enterprise knowledge) has a first version of the docs website. `README.md` is the source of truth for scope.

## Commands

- Backend tests: `cd backend && uv run pytest`
- Backend dev server: `cd backend && OHARA_DATA_DIR=.data uv run uvicorn ohara.main:app --reload`
- Frontend dev server: `cd frontend && npm run dev` (proxies `/api` to port 8000)
- Frontend build and type check: `cd frontend && npm run build`
- Full app: `OHARA_URL=http://localhost:8000 docker compose up --build`

## Layout

- `backend/ohara/`: FastAPI app. `main.py` holds routes, `github.py` the GitHub App calls, `docs.py` the docs snapshot and navigation, `sessions.py` sign-in and access checks (sessions are saved in the data volume so they survive restarts), `store.py` the settings file in the data volume.
- `frontend/src/`: React app. `Setup.tsx` is the setup page, `Gate.tsx` the sign-in screen, `Docs.tsx` the docs reader, `styles.css` the design tokens and styles. The UI follows the brand guidelines, style guide, and UI kit in the `design/` folder of the project's docs repository.
- The Docker image builds the frontend and serves it from FastAPI. All state lives in the `/data` volume.

## Product

Ohara is an open-source enterprise documentation manager. AI keeps documentation and engineering guidelines up to date, and a human approves every change.

- **Docs as code:** documentation lives in a configurable GitHub repository. Every change goes through a PR review workflow.
- **Access layers:** an HTML UI for reading and configuration, and an MCP server for AI agents and coding assistants.
- **Roadmap:** an AI chat over the docs.
- **Access control:** the website uses GitHub SSO and mirrors the docs repository's access rights. A public repository means a public website. A private repository requires sign-in, and only users with access to the repository can read the website.
- **Ingestion:** a Claude agent imports existing docs through MCP (Jira, Confluence, GitHub, Google Drive). It submits them as PRs, with a review for security and prompt injection.
- **Planned commands:**
  - `/ohara-init` configures the active project.
  - `/ohara-ingest` pulls existing docs into Ohara.
  - `/ohara-review` reviews the active project against the guidelines.
- **Workflow:** architects define guidelines, the coding assistant proposes an architecture for each new feature, architects and engineers review it, the assistant builds from the approved plan and updates the docs, and engineers review the result.

## Stack

- Frontend: React with Vite.
- Backend: Python with FastAPI.
- Deployment: Docker Compose, so anyone can self-host on any platform. The domain is configurable.
- GitHub integration: one GitHub App, created through the manifest flow from Ohara's setup page, then installed on the docs repository. It handles sign-in, read access to the docs repository, and merge events that trigger rebuilds.
- Access checks: for a private docs repository, the backend re-checks each user's repository access with GitHub every 5 minutes. A user whose access is removed loses the website within 5 minutes.
- Docs repository format: plain Markdown files with no config file. The folder tree becomes the site menu, and each page's first heading is its title. Optional front matter sets the order.
- Configuration: the domain is the only environment variable in Docker Compose. On first launch, a setup page creates the GitHub App, and the admin picks the docs repository when installing it. Settings are saved in a Docker volume.
- First version: the setup page, GitHub sign-in with access that mirrors the docs repository, docs rendering, and a rebuild on each merge. The MCP server and AI chat come later.

## Open source

Ohara is an open-source project. Never commit anything specific to one company, deployment, or person: no hosting provider, domain, repository name, or credentials. Make it configurable instead.

## Repositories

- This repo holds the application code, including the HTML website. Never add documentation to it.
- Documentation lives in a separate, configurable docs repository. Each company points Ohara to its own repository. Never hard-code a docs repository name.
- A merge to `main` in the docs repository triggers a site rebuild here.

## Conventions

- Use Conventional Commits (`docs:`, `chore:`, …).
- Keep `README.md` focused on principles and features. Implementation details, architecture diagrams, and tech stack tables were removed from it on purpose.
