---
order: 2
---

# Install

Ohara runs as one Docker container. Setup takes about five minutes and happens in the browser.

## Requirements

- Docker with Docker Compose.
- A GitHub account or organization that owns the docs repository, and permission to create a GitHub App there.
- A docs repository on GitHub. It can be empty: Ohara shows how to start.
- For webhooks, sign-in for coding assistants, and secure cookies: an `https://` address that GitHub can reach. A local run works without it, with the limits listed below.

## Quick start

1. Get the code and set the address people will use to open Ohara:

   ```bash
   git clone https://github.com/ntrossat/ohara.git
   cd ohara
   cp .env.example .env
   # edit OHARA_URL in .env, such as https://docs.acme.com
   ```

2. Start Ohara:

   ```bash
   docker compose up -d
   ```

3. Open `OHARA_URL`. Ohara shows the setup page.

`OHARA_URL` is the only setting. Everything else is configured in the browser and saved in the data volume.

## Setup

1. **Create the GitHub App.** Enter the organization that owns the docs repository, or leave the field empty for a personal account, then click **Create GitHub App**. GitHub shows the app's name and permissions. You can rename it, then confirm.
2. **Install the app.** GitHub asks where to install it. Pick the docs repository and the code repositories that Ohara should follow. You can add more later.
3. **Choose the docs repository.** Back in Ohara, pick the repository that holds the docs and click **Use this repository**. With a single repository, Ohara skips this step. If GitHub doesn't send you back, click **Check again**.
4. **Done.** Ohara downloads the repository and opens the website.

The app asks for these permissions:

| Permission | Why |
|---|---|
| Metadata: read | List the repositories and read their visibility |
| Contents: write | Download the docs, open proposal branches, and commit synced docs |
| Pull requests: write | Open, merge, and close docs pull requests |

It subscribes to `push`, `pull_request`, and `repository` events. The app is private: only the account that created it can install it.

## Serve Ohara over HTTPS

Put Ohara behind a reverse proxy that terminates TLS and forwards to port `8000`. Ohara trusts the proxy's `X-Forwarded-*` headers. With an `https://` address, Ohara marks its cookies `Secure` and enables sign-in for coding assistants.

## Serve Ohara under a path

`OHARA_URL` can include a path, such as `https://acme.com/docs`. Ohara then serves the website, the API, and the MCP server under that path, and redirects the rest of the host there. OAuth discovery for coding assistants stays at the root of the host, where clients look for it: `/.well-known/oauth-authorization-server/docs` and `/.well-known/oauth-protected-resource/docs/mcp`.

To move an existing instance to a path, update the app's settings on GitHub: the callback URL to `OHARA_URL/api/auth/callback` and the webhook URL to `OHARA_URL/api/github/webhook`. Coding assistants reconnect at `OHARA_URL/mcp`.

## Local runs

With `OHARA_URL=http://localhost:8000`, Ohara works for trying it out, with these limits:

| Feature | Local run |
|---|---|
| Website and setup | Works |
| Webhooks | GitHub can't reach the address: the docs update when Ohara restarts, and code changes are not flagged or synced |
| Sign-in for coding assistants | Works on `localhost` |
| App name | Gets a random suffix, since GitHub App names are unique |

## Next steps

- [Lay out the docs repository](../configure/docs-repository.md).
- [Connect code repositories](../configure/code-repositories.md).
- [Connect a coding assistant](../use/coding-assistants.md).
- [Operate Ohara in production](operate.md).
