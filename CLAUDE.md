# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Status

Pre-code: the repo only holds `README.md` and `LICENSE` (Apache-2.0). No build, lint, or test commands exist yet — add them here once the backend and frontend are scaffolded.

## What UNITED is

An open-source enterprise documentation manager. **AI-generated, human-controlled**: AI agents draft and update documentation, but nothing is published without a human approving a GitHub pull request.

Core invariant: **GitHub is the single source of truth.** Every write path (ingestion agent, MCP proposals from coding assistants) ends as a pull request — never a direct commit to the documentation repo. Docs are Markdown files with frontmatter; the documentation repository is configurable.

## Planned architecture

- **Ingestion agent** (Claude Agent SDK) — imports docs from external sources (Jira, Confluence, GitHub, Google Drive…) via MCP, runs a prompt-injection review on imported content, and opens PRs.
- **REST API** (Python, FastAPI) — reads from the GitHub documentation repo; serves the UI and the MCP server.
- **MCP server** — lets coding assistants read enterprise guidelines and propose changes as PRs; assistants must update documentation on every code PR. Also exposes an onboarding command that configures an existing project to use the main UNITED repo as its doc/guideline source.
- **Frontend** (React, Vite) — static HTML site generated from the repo for reading and configuration, plus an AI chat over the documentation.

Data flow: Sources → Agent → PR → human merge → GitHub repo → API → UI / MCP.
