---
order: 1
---

# How Ohara works

This page explains the ideas behind Ohara. Each section links to the page with the full details.

## The docs repository

Ohara reads its pages from one GitHub repository of Markdown files, the docs repository. There is no database of pages and no editor: the repository is the source of truth.

- The folder tree is the menu. A page's first heading is its title.
- Optional front matter sets the order and tracks freshness.
- Every change goes through a pull request, so the full history and review trail stay on GitHub.

See [Docs repository](configure/docs-repository.md).

## The GitHub App

Each Ohara instance creates its own GitHub App during setup. The app does everything Ohara needs on GitHub:

- signs people in with GitHub;
- downloads the docs repository;
- receives events (pushes, pull requests, repository changes) through a webhook;
- opens, merges, and closes the pull requests that Ohara manages.

You install the app on the docs repository and on the code repositories that Ohara should follow.

## Two ways to read

| Layer | For | Address |
|---|---|---|
| Website | People | `OHARA_URL` |
| MCP server | AI agents and coding assistants | `OHARA_URL/mcp` |

Both serve the same pages, with the same access rules.

## Proposals

AI never edits the docs directly. A coding assistant calls the `propose_change` tool, and Ohara opens a pull request on the docs repository with the new pages. The pull request is opened by the GitHub App, so the person who asked for it can still review and approve it.

## Docs that merge with the code

When a proposal comes from a code branch, such as `feature/billing` in the `api` repository, its pages go to the `api/feature/billing` branch of the docs repository. When the code pull request merges, Ohara merges the docs pull request. When it closes without merging, Ohara closes the docs pull request.

Folders the team guards in a `CODEOWNERS` file, such as guidelines, go to a separate pull request that always needs a human review.

See [Code repositories](configure/code-repositories.md#merge-docs-with-the-code).

## Freshness

Each page can say who owns it, when a human last verified it, and which code it describes:

```yaml
---
owner: ada
verified: 2026-03-01
covers: [acme/api:src/billing/*]
---
```

A page is stale when its `verified` date is more than 180 days old, or when a push changed the code it covers. Assistants see stale pages and propose updates. Merging a proposal verifies the page.

## Docs that live with the code

A code repository can keep its own docs next to the code, so they change in the same pull request. With a `.ohara.yml` at its root, Ohara syncs them into `apps/<repository name>/` of the docs repository on each push. Synced pages link back to their source file, and proposals for them go to the code repository.

See [Code repositories](configure/code-repositories.md#sync-docs-from-a-code-repository).

## Access

The website and the MCP server follow the docs repository's visibility:

| Docs repository | Who can read |
|---|---|
| Public | Everyone, no sign-in |
| Private | People who can read the repository on GitHub, after signing in |

See [Access](configure/access.md).

## Glossary

| Term | Meaning |
|---|---|
| Docs repository | The GitHub repository Ohara reads its pages from |
| Code repository | Any other repository the GitHub App is installed on |
| Snapshot | Ohara's local copy of the docs repository's default branch |
| Proposal | A change sent through `propose_change`, which becomes a pull request |
| Stale page | A page verified more than 180 days ago, or whose covered code changed |
| Synced page | A page under `apps/`, copied from a code repository |
| Guideline | A page that sets engineering rules, such as the API style or the design system |
