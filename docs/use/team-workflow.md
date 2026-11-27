---
covers: [ntrossat/ohara:backend/ohara/mcp_server.py]
verified: 2026-10-09
---

# Team workflow

Ohara supports one loop: guidelines guide the code, and the code keeps the docs current. AI does the writing. People decide.

## The loop

1. **Architects write the guidelines** in the docs repository, through pull requests like any other change. A GitHub `CODEOWNERS` file can keep the guideline folders under their review.
2. **The coding assistant plans** each feature: it reads the guidelines and docs that apply, proposes an architecture, and names the guidelines it relies on.
3. **Architects and engineers review the plan.**
4. **The assistant builds** from the approved plan, then checks the change against the guidelines and fixes what doesn't follow them.
5. **The assistant updates the docs** in the same change: it edits the project's synced docs, and proposes every other affected page in one `propose_change`. The docs pull request links go in the code pull request's description.
6. **Engineers review the code and its docs together,** and merge both pull requests. The docs pull request can be read and approved on Ohara's website, under **Changes**.

`/ohara:init` writes this loop into each project's `.claude/rules/ohara.md` (`AGENTS.md` for other assistants), so every assistant follows it.

## Roles

| Role | Does | Uses |
|---|---|---|
| Architect | Writes and approves guidelines | The docs repository, `CODEOWNERS`, `/ohara:review` |
| Engineer | Reviews plans, code, and its docs | Pull requests on GitHub, and **Changes** on the website |
| Coding assistant | Plans, builds, checks, and proposes doc updates | The MCP server and the `/ohara:*` commands |
| Ohara admin | Installs Ohara and connects repositories | The setup page and the GitHub App's settings |

## Review changes on the website

**Changes**, in the website's menu, lists the open pull requests of the docs repository, with a count of those waiting. Open one to read each page as it will be: removed text is struck, added text is highlighted, the unchanged sections are folded, and the description says why. **Approve change** merges the pull request as you, so it needs write access to the docs repository, and GitHub's rules on the repository still apply: when a rule blocks the merge, Ohara says which. **View on GitHub** opens the pull request, to comment or to see other files.

## Keep the docs fresh

- Run `/ohara:update` after a change that touched behavior the docs describe.
- Add `covers` to project pages, so pushes flag them when their code changes.
- Ask an assistant to go through `stale_pages` from time to time. A stale page that still matches the code only needs to be proposed unchanged: merging it verifies it. A synced page under `repositories/` is verified by changing its `verified` date in the code repository.

## Bring existing docs in

Run `/ohara:ingest` and name the sources. The assistant maps what already exists, plans the structure, waits for approval, then proposes one pull request per folder or topic, each with its sources and what it removed for security.
