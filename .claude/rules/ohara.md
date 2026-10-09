# Ohara instructions

Ohara, reached through the `ohara` MCP server in `.mcp.json`, is the source of truth for documentation and engineering guidelines. This project's own docs live in `docs/` and Ohara syncs them: update them in the same change as the code. Every other page lives in Ohara: propose changes to it, never add it to this repository.

Guidelines:

- `guidelines/principles`: product principles: beautiful, focused, simple by design, AI writes and humans approve, open source.
- `guidelines/backend`: Python and FastAPI with `uv`: structure, style, state, requests and errors, external APIs.
- `guidelines/frontend`: React, TypeScript, and Vite: structure, paths, styles, behavior, checks.
- `guidelines/security`: access, tokens and secrets, requests, untrusted content, reporting.
- `guidelines/testing`: what to test, how, and in CI.
- `guidelines/git`: branches, pull requests, Conventional Commits, CI and CD.
- `guidelines/writing-docs`: where docs live, format, and voice.
- `references/fastapi`: the official FastAPI user guide.
- `design`: index of the design pages, the `tokens.css` design tokens, the logo files, and the UI mockups.
- `design/brand`: name, logo, colors, typefaces, and voice.
- `design/style-guide`: design tokens (color, type, spacing, shapes, layout, motion), accessibility, and copy rules.
- `design/ui-kit`: component and screen specs for the website.

Project docs, in `docs/` (synced to `apps/ohara/`):

- `docs/README.md`: what Ohara is and how it works, for engineers, and a glossary.
- `docs/install/`: installing, setup, HTTPS, paths, and operating (data, updates, CD, troubleshooting).
- `docs/configure/`: the docs repository layout, code repositories (covers, docs pull requests from a code branch, `.ohara.yml` sync), and access.
- `docs/use/`: coding assistants, the `/ohara:*` commands, chat apps, and the team workflow.
- `docs/developers/`: architecture, API, development, and customizing.

Workflow:

- Before planning a change, read the guidelines and docs that apply, and search Ohara for anything else relevant. Say when a page you rely on is stale.
- Propose an architecture that follows the guidelines, and name the guidelines it relies on.
- After the change, check it against the guidelines and fix what does not follow them.
- Then update `docs/` in the same change, and propose updates to every other page the change affects in one `propose_change`, with the project `ohara` and the active git branch, so each code branch gets a single pull request to review. Put the docs pull request links in the code pull request's description.
