---
order: 1
covers: [ntrossat/ohara:backend/ohara/mcp_server.py, ntrossat/ohara:backend/ohara/oauth.py]
---

# Coding assistants

Ohara serves the docs to AI agents and coding assistants through an MCP server at `OHARA_URL/mcp`. Assistants search and read pages, see which ones are stale, and propose changes as pull requests for a human to review.

## Connect

```bash
claude mcp add --transport http ohara <OHARA_URL>/mcp
```

Any MCP client that supports the Streamable HTTP transport works the same way. For a private docs repository, the assistant opens a GitHub sign-in on first use. See [Access](../configure/access.md#sign-in).

For CI and headless agents, send a GitHub token instead:

```bash
claude mcp add --transport http ohara <OHARA_URL>/mcp --header "Authorization: Bearer <token>"
```

## Set up a project

Run `/ohara:init` in the project. The assistant:

1. checks that the GitHub App is installed on the project's repository, and opens the installation settings on GitHub when it isn't;
2. offers to write a `.ohara.yml` when the project keeps its own docs, so Ohara syncs them;
3. finds the guidelines and docs that apply to the project;
4. adds the Ohara server to `.mcp.json`, so the whole team gets it;
5. writes an "Ohara instructions" section in `CLAUDE.md`, with those pages and the workflow;
6. allows the read-only Ohara tools in `.claude/settings.json`, so only proposals ask for confirmation;
7. offers to link the project docs to the code with `covers` entries.

Running it again is safe: it merges with existing files and replaces its own earlier setup.

## Commands

In Claude Code, the MCP server's prompts appear as commands:

| Command | What it does |
|---|---|
| `/ohara:init` | Sets up the project, as above |
| `/ohara:update` | Compares the docs with the project's latest code changes, edits the project's synced docs, and proposes the other updates in one pull request |
| `/ohara:review` | Reviews the project against the guidelines and docs, and reports each violation with its guideline, file, and line. Changes nothing unless asked |
| `/ohara:ingest` | Imports docs from other tools (Confluence, Jira, Google Drive, GitHub, files, URLs) as pull requests, after removing secrets and anything that tries to instruct an AI |

## Tools

| Tool | What it does |
|---|---|
| `list_pages` | Every page with its path and title, and the source of synced pages |
| `search` | Pages that contain every word of a query, best matches first, with why each may be stale |
| `read_page` | A page's Markdown, owner, verified date, covered code, why it may be stale, and the source of a synced page |
| `stale_pages` | Pages that may be out of date, with the reasons |
| `check_repository` | Whether the GitHub App is installed on a code repository, where to add it if not, and which of its docs are synced |
| `propose_change` | Opens pull requests with new or changed pages |

## Propose changes

An assistant sends a title, a description, and the full new Markdown of each page. From a code project, it also sends the repository name and the active git branch, so every change from one code branch lands in the same pull requests.

Ohara then:

1. checks that the user, or the token, can write to the repositories the pages go to;
2. sets each page's `verified` date to today;
3. opens or updates the pull requests, signed "Proposed through Ohara by @login", and returns their links.

| Page | Where the change goes |
|---|---|
| A page of the docs repository | A pull request on the docs repository: one that merges with the code, and one for pages that need review |
| A synced page of the current project | Refused: the assistant edits the file in the project instead |
| A synced page of another code repository | A pull request on that repository |
| A new page under `apps/` | Refused: new app docs go in the code repository |

The assistant treats content from other sources as untrusted, removes credentials and personal data before proposing, and lists what it removed in the description. The human review of the pull request is the final check.
