---
order: 2
covers: [ntrossat/ohara:backend/ohara/appdocs.py, ntrossat/ohara:backend/ohara/appconfig.py, ntrossat/ohara:backend/ohara/freshness.py]
---

# Code repositories

Code repositories are the repositories that hold your applications. Connect them to Ohara so that:

- pushes flag the pages that describe the changed code;
- their own docs, if they keep some, are synced into the docs repository.

## Connect a repository

Install the GitHub App on it: at setup, next to the docs repository, or later in the app's installation settings on GitHub. `/ohara:init` checks this for a project and opens those settings when the app is missing.

The app is private to the account that created it, so only that account's repositories can be connected.

In code repositories, Ohara reads which files changed and the docs of those that opt in to the sync. It writes to a code repository only to open the pull requests that coding assistants propose for its synced pages.

## Flag pages when code changes

Add `covers` to a page's front matter:

```yaml
---
covers: [acme/api:src/billing/*]
---
```

When a push to the default branch of `acme/api` changes a matching file, Ohara flags the page with the date, the changed files, and a compare link. Coding assistants see the flag through `stale_pages` and propose an update. The flag stays until the page changes.

## Docs pull requests from a code branch

A coding assistant proposes doc updates from a code branch, such as `feature/billing` in the `api` repository. Ohara commits them on the `api/feature/billing` branch of the docs repository, in one pull request. Later proposals from the same branch add to it.

- The assistant puts the docs pull request link in the code pull request's description, so reviewers see the code and its docs together.
- A human reviews and merges the docs pull request. Ohara never merges or closes it.
- A branch left from a closed pull request starts again from the default branch on the next proposal.

## Sync docs from a code repository

A code repository can keep its own docs next to the code, so they change in the same pull request. It opts in with a `.ohara.yml` at its root:

```yaml
docs:
  - docs
```

Ohara then syncs those docs one way into `apps/<repository name>/` of the docs repository:

- on each push to the default branch that changes them or `.ohara.yml`, in one commit, `docs: sync owner/repo@<commit>`, with the first 12 characters of the commit, or the branch name on a full sync;
- when the app is added to the repository, and on each Ohara start.

| `.ohara.yml` | Synced |
|---|---|
| Missing | Nothing. Removing the file removes the synced folder |
| Empty, or without a `docs` key | `docs/` |
| `docs: [...]` | The listed folders and files |
| `docs:` with no value, or `docs: []` | Nothing |

- The contents of a listed folder go to the root of `apps/<repository name>/`: `docs/billing.md` becomes `apps/api/billing.md`.
- A listed file goes to the root by its name: `README.md` becomes `apps/api/README.md`, the folder's page.
- Markdown files and images (`png`, `jpg`, `jpeg`, `gif`, `svg`, `webp`) up to 1 MB each are synced, up to 500 per repository. Hidden files and symbolic links are skipped.
- Each synced page gets a `source` field, such as `source: "acme/api:docs/billing.md"`. The website's edit link and coding assistants' proposals go to that file.
- A hand edit under `apps/` in the docs repository is overwritten by the next sync. Edit synced pages in their code repository.
- Paths are normalized, so `./docs/` is `docs`. When two entries land on the same path, the first one in the list wins. Absolute paths and paths that leave the repository root are ignored.
- If `.ohara.yml` isn't valid YAML, isn't a mapping, or has a `docs` value that isn't a list, Ohara keeps the last synced copy and logs the error.
- When the docs repository's default branch is protected, Ohara opens an `ohara/sync-<repository name>` pull request instead. Merge it as is.

### Private code

Synced docs follow the docs repository's access: everyone who can read it can read them. Ohara never syncs a private code repository into a public docs repository. When a private docs repository is made public, Ohara removes the folders of private code repositories, but their files stay in the docs repository's git history.
