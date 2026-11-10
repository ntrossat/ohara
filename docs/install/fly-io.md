---
covers: [ntrossat/ohara:Dockerfile]
verified: 2026-11-10
---

# Deploy on Fly.io

Fly.io runs Ohara as one Machine with a persistent volume. The guide uses the published Docker image, so you need neither a checkout of the repository nor a build.

## Requirements

- A [Fly.io](https://fly.io/) account and the [`fly` CLI](https://fly.io/docs/flyctl/install/), signed in with `fly auth login`.
- A GitHub docs repository and permission to create a GitHub App for its owner. See [Install](README.md#requirements).

## Write the configuration

Choose a globally unique Fly app name and a region close to your readers. In a new, empty folder, create `fly.toml` with them:

```toml
app = "ohara-docs"
primary_region = "lax"

[build]
  image = "ghcr.io/ntrossat/ohara:latest"

[env]
  OHARA_URL = "https://ohara-docs.fly.dev"

[mounts]
  source = "ohara_data"
  destination = "/data"

[http_service]
  internal_port = 8000
  force_https = true
  auto_stop_machines = false
  auto_start_machines = true
  min_machines_running = 1
```

| Setting | Why |
|---|---|
| `image` | The published image. To pin a release instead of following the latest one, replace `latest` with a version such as `0.1` |
| `OHARA_URL` | The address people use. Set the final one before you create the GitHub App |
| `[mounts]` | Ohara keeps its database and docs snapshot in `/data`, so it must be a volume |
| `internal_port` | Ohara listens on port `8000` |
| `auto_stop_machines = false` | Ohara must stay up to receive GitHub webhooks and to check access and visibility every 5 minutes |

Keep this folder: every later command runs from it.

## Create the app and its volume

```bash
fly apps create ohara-docs
fly volumes create ohara_data --region lax --size 1
```

Use the app name and region from `fly.toml`, and the volume name from `[mounts]`. A volume in another region, or with another name, stays unused.

The volume holds Ohara's database, which contains GitHub App credentials and user tokens: treat it as a secret and back it up as described in [Operate](operate.md#data).

## Deploy Ohara

```bash
fly deploy --ha=false
```

`--ha=false` creates one Machine: Ohara's volume and SQLite database are not shared between replicas.

Fly provides HTTPS for the `fly.dev` address. To use a custom domain, run `fly certs add docs.acme.com`, create the [DNS records](https://fly.io/docs/networking/custom-domain/) it lists, set `OHARA_URL` to that HTTPS address in `fly.toml`, and deploy again.

## Set up Ohara

1. Open `OHARA_URL`.
2. Follow [the browser setup](README.md#setup) to create a GitHub App, install it on your repositories, and choose the docs repository.
3. Check that `OHARA_URL/api/status` answers `200`.

Use a private docs repository for a private website. Ohara mirrors its GitHub access; see [Access](../configure/access.md).

## Update and monitor

From the folder with `fly.toml`, deploy the latest image:

```bash
fly deploy --ha=false
```

The volume persists across deployments. Ohara downloads the docs again and checks code repository syncs when it starts.

Inspect the service with:

```bash
fly status
fly logs
```

To run another Ohara instance, create another folder, app, and volume, then complete setup with another GitHub App and docs repository. Don't share a volume or run multiple Machines for one instance.
