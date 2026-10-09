---
covers: [ntrossat/ohara:Makefile, ntrossat/ohara:backend/pyproject.toml, ntrossat/ohara:frontend/package.json, ntrossat/ohara:.github/workflows/ci.yml]
verified: 2026-10-09
---

# Development

## Requirements

| Tool | Version | For |
|---|---|---|
| Docker with Docker Compose | Any recent | `make dev` |
| Python | 3.14 | The backend |
| [uv](https://docs.astral.sh/uv/) | 0.5 or later | Backend dependencies and tests |
| Node.js | 24 | The frontend |

Docker alone is enough to run the whole app. Python, uv, and Node.js are for the tests and the faster split setup.

## Run it locally

The whole app, rebuilt on each code change:

```bash
cp .env.example .env     # OHARA_URL=http://localhost:8000
make dev                 # docker compose up --build --watch
```

`make init` starts over: it removes the container, the image, and the data volume, then runs `make dev`. Delete the old GitHub App on GitHub by hand, since setup creates a new one.

Or run the parts separately, for faster reloads:

```bash
# Backend on port 8000
cd backend && OHARA_URL=http://localhost:5173 OHARA_DATA_DIR=.data uv run uvicorn ohara.main:app --reload

# Frontend on port 5173, proxying /api to port 8000
cd frontend && npm install && npm run dev
```

Open `http://localhost:5173`. In this mode, the backend serves no React app, and `uvicorn` doesn't read `.env`: set `OHARA_URL` to the Vite address so GitHub sends you back to it. Vite only proxies `/api`, so connect MCP clients to the backend on port 8000, or use `make dev`.

A local address has no webhook: GitHub can't reach it, so the setup creates the app without one. Restart Ohara to pick up docs and code changes.

A local instance creates its own GitHub App. If you install it on the same repositories as a production instance, both act on them: proposals from a local instance open pull requests on the same docs repository. Use a separate docs repository for development.

## Test

```bash
cd backend && uv run pytest      # backend tests
cd frontend && npm run build     # type check and build
```

Run one file or one test:

```bash
cd backend && uv run pytest tests/test_mcp.py
cd backend && uv run pytest tests/test_mcp.py -k proposal
```

Backend tests mock GitHub with `respx`, so they need no network. Each test gets its own data directory. `tests/conftest.py` provides:

| Fixture or helper | Gives |
|---|---|
| `configure(private=True)` | A set-up instance with a docs repository and two pages |
| `client` | A test client for the website and API |
| `mcp` | A test client that runs the app's lifespan, with the docs sync turned off, for `/mcp` |
| `synced` | A test client that records docs syncs instead of running them |
| `app_credentials`, `pem` | GitHub App credentials and a private key |
| `tarball(files)` | A repository tarball, as GitHub sends it |

Add tests next to the area they cover, one file per area, and mock each GitHub call the code makes. CI runs the backend tests and the frontend build on each pull request. There is no linter or formatter: match the surrounding code.

## Project layout

```text
backend/ohara/       FastAPI app, see Architecture
backend/tests/       pytest tests, one file per area
frontend/src/        React app
docs/                these docs, synced into Ohara by .ohara.yml
.github/workflows/   CI (tests) and CD (image and deploy)
Dockerfile           builds the frontend, then the backend image
docker-compose.yml   one service and the data volume
```

## Conventions

- Work on a branch, never on `main`, and merge through a pull request.
- Use [Conventional Commits](https://www.conventionalcommits.org): `feat:`, `fix:`, `docs:`, `ci:`, `chore:`.
- Keep the README about principles and features. Implementation details go in these docs.
- Ohara is open source: never commit anything specific to one company, deployment, or person, such as a hosting provider, domain, credentials, or the name of a repository other than its own. Make it configurable.
- Interface copy follows the design guidelines in the docs repository: plain, direct, calm, no exclamation marks.
- Update these docs in the same pull request as the code they describe.

## Release

1. Merge the changes into `main`.
2. Tag the commit and push the tag:

   ```bash
   git tag v1.2.0
   git push origin v1.2.0
   ```

CI runs on the tag. Once it passes, CD publishes the image as `1.2.0`, `1.2`, and `latest`. Tags never run the deploy command. See [Operate](../install/operate.md#images).

## Contribute

Open an issue or a pull request on GitHub. See `CONTRIBUTING.md` for what makes a pull request easy to merge. Report security issues privately, as described in `SECURITY.md`.

Contributions are licensed under Apache-2.0, the project's license.
