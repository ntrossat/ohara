---
order: 3
covers: [ntrossat/ohara:backend/ohara/sessions.py, ntrossat/ohara:backend/ohara/oauth.py]
---

# Access

Ohara has no user management of its own. It mirrors the docs repository's access on GitHub.

| Docs repository | Website and MCP server |
|---|---|
| Public | Open to everyone, no sign-in |
| Private | Sign in with GitHub. Only people who can read the repository get access |

To give someone access, add them to the repository, or to a team that can read it. To remove access, remove them on GitHub: they lose the website and the MCP server within 5 minutes, when Ohara checks again.

## What people can do

| Action | Needs |
|---|---|
| Read the website and the MCP server | Read access to a private docs repository, nothing for a public one |
| Propose changes through MCP | Write access to the docs repository, or to the code repository of a synced page |
| Merge pull requests | GitHub's own rules on the repository |

## Sign-in

- **Website:** **Sign in with GitHub**. A session lasts 30 days without use.
- **Coding assistants:** the assistant opens a GitHub sign-in in the browser on first use. Ohara then asks you to approve the assistant. Approve only an assistant you started yourself: a sign-in link from someone else would give them your access.
- **CI and headless agents:** send a GitHub token as `Authorization: Bearer <token>`. It needs read access to the docs repository, and write access to propose changes.

GitHub tokens never leave the server. Coding assistants get short-lived Ohara tokens (prefix `oha_`) instead. See [Architecture](../developers/architecture.md#authentication) for the details.
