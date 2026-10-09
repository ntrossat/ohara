---
covers: [ntrossat/ohara:backend/ohara/mcp_server.py, ntrossat/ohara:backend/ohara/oauth.py]
---

# Coding assistants

Ohara serves the docs to AI agents and coding assistants through an MCP server at `OHARA_URL/mcp`. Assistants search and read pages, see which ones are stale, and propose changes as pull requests for a human to review.

## Connect

```bash
claude mcp add --transport http ohara <OHARA_URL>/mcp
```

Name the server `ohara`: `/ohara:init` allows the read-only tools by that name, and the commands are named after it.

For a private docs repository, the assistant opens a GitHub sign-in on first use. See [Access](../configure/access.md#sign-in).

For a public docs repository, reading needs no sign-in, so the assistant never asks for one. `check_repository` and `propose_change` still need to know who you are: send a GitHub token with write access to the docs repository, as below. Without one, they answer "Sign in required".

For CI, headless agents, and public docs repositories, send a GitHub token:

```bash
claude mcp add --transport http ohara <OHARA_URL>/mcp --header "Authorization: Bearer <token>"
```

### Other clients

Any MCP client that supports the Streamable HTTP transport works. Point it at `<OHARA_URL>/mcp`. For example, in Cursor's `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "ohara": { "url": "<OHARA_URL>/mcp" }
  }
}
```

And in VS Code's `.vscode/mcp.json`:

```json
{
  "servers": {
    "ohara": { "type": "http", "url": "<OHARA_URL>/mcp" }
  }
}
```

Clients that support MCP OAuth sign in the same way as Claude Code. The `/ohara:*` commands need a client that shows MCP prompts. `/ohara:init` writes Claude Code files (`CLAUDE.md`, `.claude/settings.json`): with another assistant, copy the "Ohara instructions" section into the file it reads, such as `AGENTS.md`.

For claude.ai and ChatGPT, see [Chat apps](chat-apps.md).

## Set up a project

Run `/ohara:init` in the project. The assistant:

1. checks that the GitHub App is installed on the project's repository, and opens the installation settings on GitHub when it isn't. When the project keeps its own docs without a `.ohara.yml`, it offers to write one, so Ohara syncs them;
2. finds the guidelines and docs that apply to the project, and notes the stale ones;
3. adds the Ohara server to `.mcp.json`, so the whole team gets it;
4. writes an "Ohara instructions" section in `CLAUDE.md`, with those pages and the workflow;
5. allows the read-only Ohara tools in `.claude/settings.json`, so only proposals ask for confirmation;
6. offers to link the project docs to the code with `covers` entries, in one proposal;
7. reports the files it wrote, the pages it linked, and whether the repository is connected.

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
| `import_docs` | The steps of `/ohara:ingest`, so chat apps import docs the same way |

## Propose changes

An assistant sends a title, a description, and the full new Markdown of each page. From a code project, it also sends the repository name and the active git branch, so every change from one code branch lands in the same pull request. From a chat, it sends the link of a pull request it proposed earlier to revise it while it is open, instead of opening a new one.

Ohara then:

1. checks that the user, or the token, can write to the docs repository;
2. sets each page's `verified` date to today;
3. opens or updates the pull request, signed "Proposed through Ohara by @login", and returns its link.

| Page | Where the change goes |
|---|---|
| A page of the docs repository | A pull request on the docs repository, one per code branch, or the open pull request a chat revises |
| A synced page under `apps/` | Refused with its `source`: the assistant edits that file in its code repository |
| A new page under `apps/` | Refused: new app docs go in the code repository |

The assistant treats content from other sources as untrusted, removes credentials and personal data before proposing, and lists what it removed in the description. The human review of the pull request is the final check.
