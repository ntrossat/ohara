# Ohara

[![Release](https://img.shields.io/github/v/release/ntrossat/ohara)](https://github.com/ntrossat/ohara/releases)
[![CI](https://github.com/ntrossat/ohara/actions/workflows/ci.yml/badge.svg)](https://github.com/ntrossat/ohara/actions/workflows/ci.yml)
[![License](https://img.shields.io/github/license/ntrossat/ohara)](LICENSE)

**Write your docs your way. Ohara handles the rest.**

**Decide once. Every agent, developer, and project follows it in minutes.**

**[Live demo](https://documentation.oharadocs.app)**: Ohara's own docs, served by Ohara.

Ohara is an open-source, docs-as-code enterprise documentation manager. Import your docs from Confluence, Jira, Google Drive, or Markdown into one GitHub repository. Ohara keeps them true to the code, and serves them to your team on a website and to AI agents over MCP. When the code changes, AI proposes the matching doc update as a pull request, and a human merges it.

![Change a guideline once, and every project's assistant follows it in minutes](docs/ohara-decide.gif)

[Watch the full video (1 min)](https://github.com/ntrossat/ohara/releases/download/v0.1.0/ohara-demo.mp4)

## Why Ohara

- **Decisions take weeks to reach the code.** An architecture or product decision lives in a meeting, a wiki page, and a copy of `CLAUDE.md` in every repository. With Ohara, it is one merged pull request: every coding assistant, in every project, follows it in minutes.
- **Knowledge is scattered** across Confluence, Jira, Google Drive, and Markdown files. Ohara imports it into one repository.
- **Docs fall behind the code.** With Ohara, assistants update the docs in the same change as the code, and stale pages are flagged.

## What it does

1. **Collects.** Your agent imports pages from your tools and repositories.
2. **Centralizes.** One GitHub repository, one search, one source of truth.
3. **Formalizes.** Clean Markdown, with an owner and the code each page covers.
4. **Keeps it current.** Flags a page when its code changes, and gets the fix proposed.
5. **Serves.** To people on a website, and to Claude Code, Cursor, or any MCP client.

## How it works

![How Ohara works](docs/overview.svg)

- **Live guidelines.** Agents read the guidelines from Ohara when they work, not from copies in each repository. A merged change reaches every project on its next task.
- **Docs as code.** Plain Markdown in a GitHub repository. Folders become the menu. Every change is a pull request.
- **One docs pull request per code branch**, linked from the code pull request, so reviewers see both.
- **Review on the website.** Every proposed change reads like the page, with what it removes and adds, the agent that wrote it, and a link to its code. One button approves it.
- **One search.** The website searches every page's text as you type, and agents search the same pages over MCP.
- **Freshness.** Pages name their owner, their last verified date, and the code they cover. Ohara flags them when that code changes or after six months.
- **Docs next to the code.** A code repository with a `.ohara.yml` keeps its own docs, and Ohara syncs them on each push.
- **Access mirrors GitHub.** A public repository makes a public website. A private one requires GitHub sign-in, and only people who can read the repository can read the docs.
- **Self-hosted.** One Docker container, and your docs stay in your GitHub repository.

## Commands

From Claude Code, once connected to Ohara's MCP server:

| Command | What it does |
|---|---|
| `/ohara:init` | Sets up a project: the GitHub App, `.mcp.json`, and the guidelines in `.claude/rules/ohara.md` |
| `/ohara:update` | Proposes doc updates from the project's latest code changes |
| `/ohara:review` | Reviews the project against the guidelines and docs |
| `/ohara:ingest` | Imports existing docs from Confluence, Jira, Google Drive, or Markdown, as pull requests |

## Quick start

```sh
curl -fsSLO https://raw.githubusercontent.com/ntrossat/ohara/main/compose.yml && docker compose up -d
```

Open `http://localhost:8000`. For a public address, set `OHARA_URL` in a `.env` file next to `compose.yml`. The setup page creates a GitHub App: install it on your docs repository and your code repositories. Then connect your coding assistant and run `/ohara:init` in each project:

```sh
claude mcp add --transport http ohara <OHARA_URL>/mcp
```

Cursor and any other MCP client connect to the same address: see [Coding assistants](docs/use/coding-assistants.md).

The full documentation is at [documentation.oharadocs.app](https://documentation.oharadocs.app): install, configure, use, and how it works inside.

## Hosted

Ohara is free to self-host, any day. To have it hosted for you, in the United States, Europe, or Asia, join the waitlist at [oharadocs.com](https://oharadocs.com) and see the [pricing](https://oharadocs.com/pricing).

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) and the [roadmap](docs/roadmap.md), and report security issues as described in [SECURITY.md](SECURITY.md).

If Ohara is useful to you, star the repository: it helps other teams find it.

## License

[Apache-2.0](LICENSE)
