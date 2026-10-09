# Security

Ohara holds GitHub App keys and issues access tokens, so we take security reports seriously.

## Reporting a vulnerability

Do not open a public issue. Report it privately through [GitHub's vulnerability reporting](../../security/advisories/new) on this repository.

Include the affected version or commit, the steps to reproduce, and the impact. We acknowledge reports within a few days and publish an advisory once a fix is released.

## Supported versions

Only the latest release, and `main`, receive security fixes.

## Security model

The docs cover how Ohara protects access and data:

- [Access](docs/configure/access.md): who can read and propose, and how sign-in works.
- [Architecture](docs/developers/architecture.md#authentication): sessions, OAuth for MCP clients, and tokens.
- [Operate](docs/install/operate.md#data): what the data volume holds and why to treat it as a secret.

AI-written content is never trusted on its own: every change is a pull request that a person reviews and merges. Ohara's assistant instructions ask assistants to remove secrets and anything that tries to instruct an AI, but the human review is the check that counts.
