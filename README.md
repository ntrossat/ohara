# Ohara — One place for all company knowledge, kept up to date by AI

**AI keeps your docs up to date. You approve every change.**

Ohara is an open-source documentation manager. It gathers your docs and engineering guidelines in one GitHub repository, gives every coding assistant the same guidelines, and updates the docs with each code change, through pull requests a human approves.

![The Ohara docs reader](docs/screenshot.jpg)

---

## Why Ohara

Ohara addresses three key challenges:

1. **Scattered knowledge.** Company knowledge is split across Jira, Confluence, GitHub, Google Drive, and Slack, with no single source of truth.
2. **Inconsistent coding assistants.** Every developer and every project configures their assistant on their own, so guidelines drift apart, and so does the code.
3. **Outdated documentation.** Docs fall behind the code because nobody owns the update step.

Ohara's answer:

- **One place for all knowledge.** A coding assistant or chat app imports existing docs from Jira, Confluence, GitHub, and Google Drive into a single GitHub repository, through Ohara. It is the single source of truth, readable by people on a website and by AI through MCP.
- **Shared guidelines for every developer and every project.** Architects write the guidelines once. `/ohara:init` connects any project's coding assistant to them in one command. Every assistant, in every repository, follows the same rules, and an update reaches everyone right away.
- **Docs that stay current.** Assistants propose doc updates with each code change, in one docs pull request per code branch. Stale pages are flagged automatically.
- **Humans approve every change.** AI writes the docs, and people review them.

All your company knowledge in one place, kept up to date by AI, so every coding assistant follows the same guidelines across every developer and project.

### Compared with other tools

| | Ohara | Wikis (Confluence, Notion) | Docs sites (Docusaurus, MkDocs) |
|---|---|---|---|
| Every change reviewed as a pull request | ✓ | | ✓ |
| One docs pull request per code branch | ✓ | | |
| Pages flagged when the code they describe changes | ✓ | | |
| One command connects a project's coding assistant to shared guidelines | ✓ | | |
| Access mirrors the GitHub repository | ✓ | | |
| Open source and self-hosted | ✓ | | ✓ |

---

## Principle

Every piece of documentation is updated by AI and approved by a human.

- AI ingests, writes, and proposes.
- Humans review, approve, and merge every docs pull request.
- Ohara is the single source of truth.

---

## Features

### Documentation as code
- All documentation stored in your GitHub repository
- Every change goes through a validation workflow
- Full history, review, and traceability
- The docs changes of a code branch go to one pull request, linked from the code pull request
- Code repositories can keep their own docs next to the code: Ohara shows them next to the documentation and syncs them on each push
- Configurable repository

### Freshness
- Each page can name its owner, the date a human last verified it, and the code it describes
- Pages verified more than six months ago are flagged as stale
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
- An AI assistant imports existing documentation from external sources, with its own connectors, through Ohara's MCP server:
  - Jira
  - Confluence
  - GitHub
  - Google Drive
  - and more
- Imported content is submitted as pull requests for review
- The assistant removes secrets and prompt injections, and a human reviews every pull request

### Project onboarding
- An MCP command configures an existing project to use the main Ohara repository as its documentation and guideline source


---

## Roadmap
- **AI chat** to ask questions about the documentation
- **Install from the published image**: a Compose file that runs the versioned image, so `docker compose up` starts Ohara without building it

---

## Commands
- `/ohara:init`: connect the active project's repository to the GitHub App, and configure the project to read the guidelines before planning, check its changes against them, and propose documentation updates after each change
- `/ohara:update`: propose documentation updates that match the active project's latest code changes
- `/ohara:ingest`: pull and rewrite existing documentation and guidelines into Ohara, as pull requests reviewed for secrets and prompt injection
- `/ohara:review`: review the active project against the documentation and guidelines, and report each violation with its guideline and location

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

The full documentation is in [`docs/`](docs/README.md): what Ohara does, how to install, configure, and use it, and how it works inside.

1. Clone this repository, copy `.env.example` to `.env`, and set `OHARA_URL` to the address people will use to open Ohara. It can include a path, such as `https://acme.com/docs`.
2. Run `docker compose up -d`.
3. Open Ohara, create the GitHub App from the setup page, and install it on your docs repository and your code repositories. Then choose the docs repository in Ohara.

Your docs repository holds plain Markdown files. Folders become the menu, and each page's first heading is its title. Optional front matter tracks freshness:

```yaml
---
owner: ada
verified: 2026-03-01
covers: [acme/api:src/billing/*]
---
```

Code repositories on the same installation flag the pages whose `covers` name them. A repository that opts in with a `.ohara.yml` at its root (`/ohara:init` writes one with `docs:` listing `docs`) has those docs synced one way into `apps/<repo>/` of the website on each push, without commits to the docs repository. A private code repository is never synced when the docs repository is public. Add more later in the app's installation settings on GitHub, or let `/ohara:init` open them for the project's repository. The app can write to every repository it is installed on, though in code repositories Ohara only reads their docs and which files changed.

Connect a coding assistant to the MCP server. For a private docs repository, it opens a GitHub sign-in on first use:

```sh
claude mcp add --transport http ohara <OHARA_URL>/mcp
```

Then run `/ohara:init` in the project to set it up.

For CI, headless agents, and proposals on a public docs repository, send a GitHub token: `--header "Authorization: Bearer <token>"`.

Assistants read pages and propose changes. A proposal from a code branch opens one docs pull request, and later proposals from the same branch add to it. Other proposals open their own pull request. A human reviews and merges each one. Proposing requires a signed-in user or a token with write access to the repository.

---

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md), and report security issues as described in [SECURITY.md](SECURITY.md).

---

## License

[Apache-2.0](LICENSE)
