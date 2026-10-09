---
covers: [ntrossat/ohara:frontend/src/styles.css, ntrossat/ohara:backend/ohara/mcp_server.py, ntrossat/ohara:backend/ohara/freshness.py, ntrossat/ohara:backend/ohara/appdocs.py]
---

# Customize

Most of Ohara is configured through GitHub, with no code change: the docs repository's layout, the app's installation, and `.ohara.yml` in code repositories. This page covers the changes that need code, for a fork or a contribution.

## Look and feel

The website's design lives in `frontend/src/styles.css`. Its first block defines the design tokens as CSS custom properties, mirroring `design/tokens.css` in the docs repository, with phone sizes under 860px:

| Token | Role |
|---|---|
| `--bg`, `--bg-2`, `--surface-3`, `--line` | Background, panels, small filled shapes, and borders |
| `--ink`, `--text`, `--muted` | Titles, body text, secondary text |
| `--clay`, `--clay-hover`, `--link`, `--on-clay` | The accent color, for buttons, the current page, and links, and text on it |
| `--serif`, `--sans`, `--mono` | Title, interface, and code typefaces |
| `--size-*`, `--space-*` | Type sizes and the 4px spacing scale |
| `--radius-*`, `--border` | Shapes |
| `--topbar-height`, `--menu-width`, `--content-width`, `--page-max` | Layout |
| `--ease`, `--duration` | Motion |

Change the tokens to rebrand the whole site. The logo is drawn in `Mark.tsx`. Fonts are bundled with `@fontsource` packages, so the site makes no request to a font service.

## Assistant instructions

The `/ohara:*` commands are MCP prompts in `backend/ohara/mcp_server.py`: `INIT_PROMPT`, `UPDATE_PROMPT`, `REVIEW_PROMPT`, and `INGEST_PROMPT`. Each is plain text, with `{url}` and `{repo}` filled in for the instance. Edit them to change what an assistant does, such as the sections `/ohara:init` writes in `CLAUDE.md`.

To add a command, write a new prompt, such as `ONBOARD_PROMPT`, and register it:

```python
@server.prompt(name="onboard", title="Onboard a new engineer")
def onboard() -> str:
    """Walk a new engineer through the docs that matter for this project."""
    return fill(ONBOARD_PROMPT)
```

It appears as `/ohara:onboard` in Claude Code.

## MCP tools

Tools are functions decorated with `@server.tool()` in `mcp_server.py`. The docstring is the description assistants read, so write it for them. Return a Pydantic model for structured output. Read the caller from `ctx.request_context.request.state.caller` when the tool needs a signed-in user, and raise `ToolError` with a message that says how to fix the problem.

```python
@server.tool()
async def owners(ctx: Context) -> list[dict]:
    """List each page owner and the pages they own."""
    caller: Caller | None = ctx.request_context.request.state.caller
    if not caller:
        raise ToolError("Sign in required: connect with a GitHub token that can read the docs repository")
    ...
```

`Context` comes from `mcp.server.mcpserver` and `ToolError` from `mcp.server.mcpserver.exceptions`, both already imported in `mcp_server.py`. For a public docs repository, `caller` is `None` when the client sent no token.

Access is enforced before any tool runs: for a private docs repository, only callers who can read it reach the tools.

## Sync and freshness rules

| Rule | Where |
|---|---|
| Stale after 180 days | `STALE_AFTER_DAYS` in `freshness.py` |
| Stale flags kept per page | `MAX_CHANGES` in `freshness.py` |
| Synced file types, size, and count | `TYPES`, `MAX_SIZE`, `MAX_FILES` in `appdocs.py` |
| Synced folder | `APPS` in `docs.py` |
| Folder index file names | `INDEX_NAMES` in `docs.py` |
| Ignore file name | `IGNORE_FILE` in `docs.py` |
| How long stale flags from code changes last | `DRIFT_TTL` in `freshness.py` |
| Session length without use | `TTL` in `sessions.py` |
| MCP token, refresh token, and sign-in lifetimes | `ACCESS_TTL`, `REFRESH_TTL`, `PENDING_TTL` in `oauth.py` |
| Registered MCP clients kept | `MAX_CLIENTS` in `oauth.py` |
| `.ohara.yml` format and layout | `appconfig.py` |
| Search results | `SEARCH_LIMIT` in `mcp_server.py` |
| Access check interval | `CHECK_INTERVAL` in `sessions.py` |

## Deployment

The CD workflow runs any deploy script set in the repository variable `DEPLOY_COMMAND`, so a fork deploys anywhere without changing the code. See [Operate](../install/operate.md#continuous-deployment).

## Keep it open source

A fork for one company should keep that company's details in configuration: `OHARA_URL`, the GitHub App, repository settings, and variables. That way, upstream changes merge without conflicts.
