# Ohara

**One central place for all enterprise knowledge. AI keeps your docs up to date. You approve every change.**

Ohara is an open-source documentation manager. It keeps your documentation and engineering guidelines in one GitHub repository, serves them to people on a website and to AI coding assistants through MCP, and keeps them up to date with every code change. AI proposes each update. A human approves it.

![The Ohara docs reader](screenshot.jpg)

## The problem

| Today | What it costs |
|---|---|
| Knowledge is spread across Confluence, Jira, Google Drive, GitHub, and Slack | People can't find the answer, or find three that disagree |
| Each developer configures their coding assistant alone | Assistants follow different rules, so the code drifts apart across teams |
| Docs fall behind the code | Nobody trusts the docs, so nobody reads or updates them |

## What Ohara changes

- **One source of truth.** All docs and guidelines live in one GitHub repository. Ohara imports existing content from other tools as pull requests.
- **The same rules for every assistant.** Architects write the guidelines once. One command connects any project's coding assistant to them, and an update reaches every project at once.
- **Docs that keep up with the code.** When code changes, the assistant proposes the matching doc update. Pages are flagged when the code they describe changes, or when their last check is more than six months old.
- **Humans stay in control.** Every change is a pull request that a person reviews and merges.

## Who it helps

| Role | What they get |
|---|---|
| Executives | One place to find how the company builds software, and docs they can trust because each change is reviewed |
| Architects | Guidelines that every coding assistant applies, in every repository, without copying them |
| Engineers | Docs that update with their pull requests, and an assistant that already knows the rules |
| New hires | One website to learn the systems, current because the code keeps it current |

## How it works

```text
  Architects and engineers              Coding assistants (Claude Code, ...)
           |  read                               |  read guidelines, propose updates
           v                                     v
     +-------------- Ohara (one Docker container) ---------------+
     |   Website                 MCP server                      |
     +-----------------------------+------------------------------+
                                   |  GitHub App
                                   v
     Docs repository                   Code repositories
     (Markdown, pull requests)         (pushes flag stale pages,
                                        docs change with the code)
```

1. Your docs are plain Markdown files in a GitHub repository. Folders become the menu.
2. People read them on the Ohara website. Coding assistants read them through the MCP server.
3. When an assistant changes code, it proposes the doc updates as a pull request on the docs repository, linked from the code pull request so reviewers see both.
4. Pushes to code repositories flag the pages that describe the changed code, so assistants know what to update next.

See [How Ohara works](concepts.md) for the details.

## Trust and security

- **Self-hosted.** Ohara runs as one container on your infrastructure. Your docs stay in your GitHub repository.
- **Access mirrors GitHub.** A public docs repository makes a public website. A private one requires GitHub sign-in, and only people who can read the repository can read the docs. Access is checked again every 5 minutes.
- **No AI change goes in unreviewed.** AI opens pull requests. People review and merge them.
- **Open source.** Apache-2.0 license.

## Where to go next

| I want to | Read |
|---|---|
| Understand the concepts | [How Ohara works](concepts.md) |
| Install Ohara | [Install](install/README.md) |
| Run it in production | [Operate](install/operate.md) |
| Lay out the docs repository | [Docs repository](configure/docs-repository.md) |
| Connect code repositories | [Code repositories](configure/code-repositories.md) |
| Control who reads the docs | [Access](configure/access.md) |
| Connect a coding assistant | [Coding assistants](use/coding-assistants.md) |
| Set up the team workflow | [Team workflow](use/team-workflow.md) |
| Understand the internals | [Architecture](developers/architecture.md) |
| Change or extend Ohara | [Customize](developers/customize.md) |
