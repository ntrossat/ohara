# Ohara — One central place for all enterprise knowledge

**AI-generated, human-controlled.**

Ohara is an open-source documentation manager: one central place for all enterprise knowledge. It keeps all enterprise documentation and engineering guidelines up to date using AI.

---

## Principle

Every piece of documentation is updated by AI and approved by a human.

- AI ingests, writes, and proposes.
- Humans review, approve, and merge.
- Ohara is the single source of truth.

---

## Features

### Documentation as code
- All documentation stored in your GitHub repository
- Every change goes through a validation workflow
- Full history, review, and traceability
- Configurable repository

### Freshness
- Each page can name its owner, the date a human last verified it, and the code it describes
- Pages not verified for six months are flagged as stale
- Pages are flagged when the code they describe changes
- AI assistants see which pages are stale and propose updates for review

### Multiple access layers
- **HTML** for human reading and configuration
- **MCP server** for AI agents and coding assistants

### Access control
- GitHub SSO authentication
- Website access mirrors the documentation repository:
  - Public repository: public website
  - Private repository: sign-in required, and only users with access to the repository can read the website

### Coding assistant integration
- Coding assistants access enterprise guidelines through MCP
- Assistants update technical documentation

### AI-powered ingestion
- A Claude agent imports existing documentation from external sources through MCP:
  - Jira
  - Confluence
  - GitHub
  - Google Drive
  - and more
- Imported content is submitted as pull requests for review
- Security and prompt injection review

### Project onboarding
- An MCP command configures an existing project to use the main Ohara repository as its documentation and guideline source


---

## Roadmap
- **AI chat** to ask questions about the documentation

---

## Commands
- `/ohara:init`: configure the active project to read the guidelines before planning, check its changes against them, and propose documentation updates after each change
- `/ohara-ingest`: pull and rewrite existing documentation and guidelines into Ohara
- `/ohara-review`: review the active project against the documentation and guidelines

---

## Workflow
- Architects define guidelines
- Coding assistant uses them and proposes an architecture for each new feature
- Architects and engineers review
- Coding assistant develops based on the approved plan
- Coding assistant updates the documentation
- Engineers review


---

## Getting started

1. Set `OHARA_URL` to the address people will use to open Ohara (see `.env.example`).
2. Run `docker compose up -d`.
3. Open Ohara, create the GitHub App from the setup page, and install it on your docs repository.

Your docs repository holds plain Markdown files. Folders become the menu, and each page's first heading is its title. Optional front matter tracks freshness:

```yaml
---
owner: ada
verified: 2026-03-01
covers: [acme/api:src/billing/*]
---
```

To flag pages when code changes, finish setup with only the docs repository, then add the code repositories that `covers` names to the same GitHub App installation. The app can write to every repository it is installed on, though Ohara only reads which files changed in them.

Connect a coding assistant to the MCP server. For a private docs repository, it opens a GitHub sign-in on first use:

```sh
claude mcp add --transport http ohara <OHARA_URL>/mcp
```

Then run `/ohara:init` in the project to set it up.

For CI and headless agents, send a GitHub token instead: `--header "Authorization: Bearer <token>"`.

Assistants read pages and propose changes. A proposal opens a pull request on the docs repository for a human to review. Proposing requires a signed-in user or a token with write access to the repository.

---

## Contributing

Contributions are welcome. Open an issue or submit a pull request.

---

## License

[Apache-2.0](LICENSE)
