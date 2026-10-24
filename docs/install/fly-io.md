---
covers: [ntrossat/ohara:fly.toml, ntrossat/ohara:Dockerfile]
verified: 2026-10-24
---

# Deploy on Fly.io

Fly.io runs Ohara as one Machine with a persistent volume. The guide uses the published Docker image, so you don't need to build the application or change the repository.

## Requirements

- A [Fly.io](https://fly.io/) account and the [`fly` CLI](https://fly.io/docs/flyctl/install/), signed in with `fly auth login`.
- A GitHub docs repository and permission to create a GitHub App for its owner. See [Install](README.md#requirements).

## Create the app and its volume

Choose a globally unique Fly app name and a region close to your readers:

```bash
APP=ohara-docs
REGION=lax

fly apps create "$APP"
fly volumes create ohara_data --app "$APP" --region "$REGION" --size 1
```

The volume stores Ohara's database and docs snapshot. Its database contains GitHub App credentials and user tokens: treat it as a secret and back it up as described in [Operate](operate.md#data).

## Deploy Ohara

From a checkout of the Ohara repository, deploy the published image:

```bash
fly deploy \
  --app "$APP" \
  --image ghcr.io/ntrossat/ohara:latest \
  --env "OHARA_URL=https://$APP.fly.dev" \
  --ha=false
```

The `--app` and `--env` options override the values in the checked-in `fly.toml`. Repeat them on every deployment so the instance keeps its own name and public address. `--ha=false` creates one Machine: Ohara's volume and SQLite database are not shared between replicas.

To pin a release instead of following the latest release, replace `latest` with a version such as `0.1`.

Fly provides HTTPS for the `fly.dev` address. To use a custom domain, [create its certificate and DNS records](https://fly.io/docs/networking/custom-domain/) and set `OHARA_URL` to that HTTPS address instead. Configure the final address before setting up the GitHub App.

## Set up Ohara

1. Open `https://$APP.fly.dev`, or your custom domain.
2. Follow [the browser setup](README.md#setup) to create a GitHub App, install it on your repositories, and choose the docs repository.
3. Check that `https://$APP.fly.dev/api/status` returns successfully.

Use a private docs repository for a private website. Ohara mirrors its GitHub access; see [Access](../configure/access.md).

## Update and monitor

Deploy an update with the same app and public address:

```bash
fly deploy \
  --app "$APP" \
  --image ghcr.io/ntrossat/ohara:latest \
  --env "OHARA_URL=https://$APP.fly.dev" \
  --ha=false
```

The volume persists across deployments. Ohara downloads the docs again and checks code repository syncs when it starts.

Inspect the service with:

```bash
fly status --app "$APP"
fly logs --app "$APP"
```

To run another Ohara instance, create another Fly app and volume, then complete setup with another GitHub App and docs repository. Don't share a volume or run multiple containers for one instance.
