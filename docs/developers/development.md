---
order: 3
covers: [ntrossat/ohara:Makefile, ntrossat/ohara:backend/pyproject.toml, ntrossat/ohara:frontend/package.json, ntrossat/ohara:.github/workflows/ci.yml]
---

# Development

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
cd backend && OHARA_DATA_DIR=.data uv run uvicorn ohara.main:app --reload

# Frontend on its own port, proxying /api to port 8000
cd frontend && npm run dev
```

A local instance creates its own GitHub App. If you install it on the same repositories as a production instance, both act on them: a local instance with the sync feature commits to the same docs repository. Use a separate docs repository for development.

## Test

```bash
cd backend && uv run pytest      # backend tests
cd frontend && npm run build     # type check and build
```

Backend tests mock GitHub with `respx`, so they need no network. `tests/conftest.py` provides a configured instance (`configure`), app credentials, a test client, and a tarball helper. CI runs both on each pull request.

## Project layout

```
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
- Ohara is open source: never commit anything specific to one company, deployment, or person, such as a hosting provider, domain, repository name, or credentials. Make it configurable.
- Interface copy follows the design guidelines in the docs repository: plain, direct, calm, no exclamation marks.
- Update these docs in the same pull request as the code they describe.

## Contribute

Open an issue or a pull request on GitHub. Report security issues privately, as described in `SECURITY.md`.
