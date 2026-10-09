---
covers: [ntrossat/ohara:Dockerfile, ntrossat/ohara:docker-compose.yml, ntrossat/ohara:Makefile, ntrossat/ohara:backend/ohara/config.py, ntrossat/ohara:frontend/src/Setup.tsx]
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

1. **Create the GitHub App.** Enter the organization that owns the docs repository, or leave the field empty for a personal account, then click **Create GitHub App**. GitHub shows the app's name, `Ohara // ` followed by the host, and its permissions. You can rename it, then confirm.
2. **Install the app.** GitHub asks where to install it. Pick the docs repository and the code repositories that Ohara should follow. You can add more later.
3. **Choose the docs repository.** Back in Ohara, pick the repository that holds the docs and click **Use this repository**. With a single repository, Ohara skips this step. If GitHub doesn't send you back, click **Check again**.
4. **Done.** Ohara downloads the repository and opens the website.

The app asks for these permissions:

| Permission | Why |
|---|---|
| Metadata: read | List the repositories and read their visibility |
| Contents: write | Download the docs and code repositories' docs, and open proposal branches |
| Pull requests: write | Open docs pull requests |

It subscribes to `push` and `repository` events. The app is private: only the account that created it can install it.

## Serve Ohara over HTTPS

Put Ohara behind a reverse proxy that terminates TLS and forwards to port `8000`. Ohara trusts the proxy's `X-Forwarded-*` headers. With an `https://` address, Ohara marks its cookies `Secure` and enables sign-in for coding assistants.

## Serve Ohara under a path

`OHARA_URL` can include a path, such as `https://acme.com/docs`. Ohara then serves the website, the API, and the MCP server under that path, and redirects the rest of the host there. OAuth discovery for coding assistants stays at the root of the host, where clients look for it: `/.well-known/oauth-authorization-server/docs` and `/.well-known/oauth-protected-resource/docs/mcp`.

To move an existing instance to a path, update the app's settings on GitHub: the callback URL to `OHARA_URL/api/auth/callback`, the Setup URL to `OHARA_URL/api/setup/installed`, and the webhook URL to `OHARA_URL/api/github/webhook`. Coding assistants reconnect at `OHARA_URL/mcp`.

## Local runs

With `OHARA_URL=http://localhost:8000`, Ohara works for trying it out, with these limits:

| Feature | Local run |
|---|---|
| Website and setup | Works |
| Webhooks | GitHub can't reach the address: the docs update when Ohara restarts, and code changes are not flagged or synced |
| Sign-in for coding assistants | Works on `localhost` |
| App name | Gets a random suffix, such as `Ohara // localhost#be8c07`, since GitHub App names are unique |

An app created on an address GitHub can't reach has no webhook and no events. To move such an instance to a public address, start over with `make init`, which removes the data and creates a new app; delete the old app on GitHub by hand. You can instead add the webhook URL (`OHARA_URL/api/github/webhook`) and the `push` and `repository` events in the app's settings, but Ohara checks each delivery against the webhook secret it saved when it created the app. If GitHub gave the app no secret, Ohara rejects the deliveries with `401`, and `make init` is the only way.

## Next steps

- [Lay out the docs repository](../configure/docs-repository.md).
- [Connect code repositories](../configure/code-repositories.md).
- [Connect a coding assistant](../use/coding-assistants.md).
- [Operate Ohara in production](operate.md).
