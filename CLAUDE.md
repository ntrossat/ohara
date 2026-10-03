# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Status

UNITED (UNIfied Technical Entreprise Documentation) is at the concept stage. The repo holds only `README.md` and `LICENSE` (Apache-2.0), so there are no build, lint, or test commands yet. `README.md` is the source of truth for scope.

## Product

UNITED is an open-source enterprise documentation manager. AI keeps documentation and engineering guidelines up to date, and a human approves every change.

- **Docs as code:** documentation lives in a configurable GitHub repository. Every change goes through a PR review workflow.
- **Access layers:** an HTML UI for reading and configuration, an MCP server for AI agents and coding assistants, and an AI chat over the docs.
- **Ingestion:** a Claude agent imports existing docs through MCP (Jira, Confluence, GitHub, Google Drive). It submits them as PRs, with a review for security and prompt injection.
- **Planned commands:**
  - `/united-init` configures the active project.
  - `/united-ingest` pulls existing docs into UNITED.
  - `/united-review` reviews the active project against the guidelines.
- **Workflow:** architects define guidelines, the coding assistant proposes an architecture for each new feature, architects and engineers review it, the assistant builds from the approved plan and updates the docs, and engineers review the result.

## Conventions

- Use Conventional Commits (`docs:`, `chore:`, …).
- Keep `README.md` focused on principles and features. Implementation details, architecture diagrams, and tech stack tables were removed from it on purpose.
