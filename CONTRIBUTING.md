# Contributing

Thanks for helping with Ohara. Issues and pull requests are welcome.

## Before you start

- For a bug, open an issue with the steps to reproduce, what you expected, and what happened. Include the Ohara version or commit, and the logs from `docker compose logs`.
- For a new feature, open an issue first. Ohara stays focused on a few core features, so agree on the idea before writing the code.
- Report security issues privately, as described in [SECURITY.md](SECURITY.md).

## Make a change

1. Fork the repository and create a branch from `main`.
2. Set up your environment and run Ohara locally: see [Development](docs/developers/development.md).
3. Make the change, with tests for the backend.
4. Update the docs in `docs/` in the same pull request as the code they describe.
5. Check that it passes:

   ```bash
   cd backend && uv run pytest
   cd frontend && npm run build
   ```

6. Open a pull request against `main`. Describe what changes and why.

## Conventions

- Commit messages follow [Conventional Commits](https://www.conventionalcommits.org): `feat:`, `fix:`, `docs:`, `ci:`, `chore:`.
- Never commit anything specific to one company, deployment, or person, such as a hosting provider, a domain, credentials, or the name of another repository. Make it configurable.
- Interface copy is plain, direct, and calm: sentence case, buttons that say what happens, no exclamation marks, no apologies.
- Keep `README.md` about principles and features. Implementation details go in `docs/`.

## License

By contributing, you agree that your contributions are licensed under the [Apache-2.0 license](LICENSE).
