---
covers: [ntrossat/ohara:backend/pyproject.toml, ntrossat/ohara:frontend/package.json]
---

# Developers

How Ohara is built, and how to change it.

| Page | Covers |
|---|---|
| [Architecture](architecture.md) | Components, state, authentication, the sync, and how a request flows |
| [API](api.md) | HTTP routes, GitHub webhook events, and the MCP server's tools and prompts |
| [Development](development.md) | Run Ohara locally, test it, and contribute |
| [Customize](customize.md) | Change the look, the assistant instructions, the tools, and the sync rules |

## Stack

| Part | Technology |
|---|---|
| Backend | Python 3.14, FastAPI, the MCP Python SDK, httpx, PyYAML, PyJWT, SQLite |
| Frontend | React 19 with Vite, React Router, react-markdown |
| Packaging | One Docker image: the frontend is built, then served by FastAPI |
| CI and CD | GitHub Actions: tests on each pull request, push to `main`, and `v*` tag, then an image for `main` and `v*` tags once they pass, and an optional deploy command |
