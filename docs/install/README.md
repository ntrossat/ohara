---
covers: [ntrossat/ohara:Dockerfile, ntrossat/ohara:docker-compose.yml, ntrossat/ohara:Makefile, ntrossat/ohara:backend/ohara/config.py, ntrossat/ohara:frontend/src/Setup.tsx]
---

# Install

Ohara runs as one Docker container. Setup takes about five minutes and happens in the browser.

## Requirements

- Docker with Docker Compose.
- A GitHub account or organization on github.com that owns the docs repository, and permission to create a GitHub App there. GitHub Enterprise Server is not supported.
- A docs repository on GitHub. It can be empty: Ohara shows how to start.
- For webhooks, sign-in for coding assistants and chat apps, and secure cookies: an `https://` address that GitHub can reach. A local run works without it, with the limits listed below.

Ohara is light: a small server and a SQLite database. It holds each repository download in memory while it reads it, so give it memory for the largest repository it reads, plus a margin.

### Limits

- One instance serves one docs repository, from one GitHub App installation on one account.
- Run one container per instance. The database and the docs snapshot live in its volume, so replicas don't share them.
- Ohara builds the image from source. A Compose file that runs the published image is on the roadmap.

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

## Settings

`OHARA_URL` is the only setting. Everything else is configured in the browser and saved in the data volume.

| Variable | Default | Meaning |
|---|---|---|
| `OHARA_URL` | Required | The public address of Ohara, without a trailing slash. It can include a path |
| `OHARA_DATA_DIR` | `/data` | Where Ohara keeps its data. For a run outside Docker |
| `OHARA_STATIC_DIR` | The built React app in the image | Where the React app lives. For a run outside Docker |

Docker Compose reads `OHARA_URL` from `.env` and passes only that variable to the container. Outside Docker, set the variables in the shell: nothing reads `.env`.

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

It subscribes to `push` and `repository` events, when `OHARA_URL` looks public. The app is private: only the account that created it can install it.

GitHub App names are unique across GitHub. The name is cut to 34 characters, so with a long host, rename the app on GitHub's confirmation page.

## Serve Ohara over HTTPS

Put Ohara behind a reverse proxy that terminates TLS and forwards to port `8000`. Ohara trusts the proxy's `X-Forwarded-*` headers. With an `https://` address, Ohara marks its cookies `Secure` and enables sign-in for coding assistants.

Ohara trusts those headers from any address, so only the proxy should reach port `8000`. Docker Compose publishes it on every interface: on a shared host, publish it on `127.0.0.1:8000:8000` instead, or block it with a firewall.

For a health check, use `GET OHARA_URL/api/status`. It answers `200` without sign-in, also before setup.

## Serve Ohara under a path

`OHARA_URL` can include a path, such as `https://acme.com/docs`. Ohara then serves the website, the API, and the MCP server under that path, and redirects the rest of the host there. OAuth discovery for coding assistants stays at the root of the host, where clients look for it: `/.well-known/oauth-authorization-server/docs` and `/.well-known/oauth-protected-resource/docs/mcp`. When another app serves the rest of the host, the proxy must forward these two paths to Ohara too.

To move an existing instance to a path, update the app's settings on GitHub: the callback URL to `OHARA_URL/api/auth/callback`, the Setup URL to `OHARA_URL/api/setup/installed`, and the webhook URL to `OHARA_URL/api/github/webhook`. Coding assistants and chat apps reconnect at `OHARA_URL/mcp`: their earlier sign-ins stop working.

## Local runs

With `OHARA_URL=http://localhost:8000`, Ohara works for trying it out, with these limits:

| Feature | Local run |
|---|---|
| Website and setup | Works |
| Webhooks | None: the docs and code repositories' docs update when Ohara restarts, and pushes flag no pages |
| Sign-in for coding assistants | Works on `localhost` |
| App name | Gets a random suffix, such as `Ohara // localhost#be8c07`, since GitHub App names are unique |

Ohara creates the app without a webhook when `OHARA_URL` is `localhost`, an IP address that isn't public, a host without a dot, or a host ending in `.local`, `.localhost`, or `.internal`. Any other host gets a webhook, even if GitHub can't reach it: an intranet host gets the deliveries refused, and Ohara only updates on restart.

An app created without a webhook has no events. To move such an instance to a public address, start over: delete the old app on GitHub, run `docker compose down -v`, set the new `OHARA_URL`, and run `docker compose up -d`. Setup then creates a new app. You can instead add the webhook URL (`OHARA_URL/api/github/webhook`) and the `push` and `repository` events in the app's settings, but Ohara checks each delivery against the webhook secret it saved when it created the app. If GitHub gave the app no secret, Ohara rejects the deliveries with `401`, and starting over is the only way.

## Next steps

- [Lay out the docs repository](../configure/docs-repository.md).
- [Connect code repositories](../configure/code-repositories.md).
- [Connect a coding assistant](../use/coding-assistants.md).
- [Operate Ohara in production](operate.md).
