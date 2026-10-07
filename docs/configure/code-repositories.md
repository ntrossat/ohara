---
order: 2
covers: [ntrossat/ohara:backend/ohara/appdocs.py, ntrossat/ohara:backend/ohara/appconfig.py, ntrossat/ohara:backend/ohara/codeowners.py, ntrossat/ohara:backend/ohara/freshness.py]
---

# Code repositories

Code repositories are the repositories that hold your applications. Connect them to Ohara so that:

- pushes flag the pages that describe the changed code;
- docs pull requests merge with the code that updated them;
- their own docs, if they keep some, are synced into the docs repository.

## Connect a repository

Install the GitHub App on it: at setup, next to the docs repository, or later in the app's installation settings on GitHub. `/ohara:init` checks this for a project and opens those settings when the app is missing.

The app is private to the account that created it, so only that account's repositories can be connected.

In code repositories, Ohara reads which files changed, which pull requests closed, and the docs of those that opt in to the sync. It writes to a code repository only to open the pull requests that coding assistants propose for its synced pages.

## Flag pages when code changes

Add `covers` to a page's front matter:

```yaml
---
covers: [acme/api:src/billing/*]
---
```

When a push to the default branch of `acme/api` changes a matching file, Ohara flags the page with the date, the changed files, and a compare link. Coding assistants see the flag through `stale_pages` and propose an update. The flag stays until the page changes.

## Merge docs with the code

A coding assistant proposes doc updates from a code branch, such as `feature/billing` in the `api` repository. Ohara sorts the pages with the docs repository's `CODEOWNERS` file:

| Pages | Pull request | Merged |
|---|---|---|
| With no code owner | `api/feature/billing` | Automatically, when the code pull request merges into the default branch |
| With a code owner | `api/feature/billing-review` | By a human, after review |

- When the code pull request closes without merging, Ohara closes the automatic docs pull request.
- Until then, the automatic pull request stays open: anyone can review, edit, or close it.
- Before merging, Ohara checks the files against `CODEOWNERS` again. If a file now has a code owner, or the merge fails, it leaves a comment and a human merges.
- The assistant puts the docs pull request links in the code pull request's description, so approving the code also approves its docs.

Proposals that don't come from a code branch, such as imports, always go to review.

### Choose the folders that need review

Add a `CODEOWNERS` file to the docs repository:

```
# Guidelines and design need review
/guidelines/    @acme/architects
/design/        @acme/design
```

| Goal | `CODEOWNERS` |
|---|---|
| Review everything (the default) | No `CODEOWNERS` file, or `* @acme/docs` |
| Review some folders, merge the rest with the code | One line per guarded folder, as above |
| Review everything except one folder | `* @acme/docs`, then `/architecture/` with no owner. The last matching line wins |

Patterns follow GitHub's rules. Branch protection that requires approvals on the docs repository also blocks the automatic merges: Ohara then comments and a human merges.

## Sync docs from a code repository

A code repository can keep its own docs next to the code, so they change in the same pull request. It opts in with a `.ohara.yml` at its root:

```yaml
docs:
  - docs
```

Ohara then syncs those docs one way into `apps/<repository name>/` of the docs repository:

- on each push to the default branch that changes them or `.ohara.yml`, in one commit, `docs: sync owner/repo@sha`;
- when the app is added to the repository, and on each Ohara start.

| `.ohara.yml` | Synced |
|---|---|
| Missing | Nothing. Removing the file removes the synced folder |
| Without a `docs` list, or empty | `docs/` |
| `docs: [...]` | The listed folders and files |
| `docs: []` | Nothing |

- The contents of a listed folder go to the root of `apps/<repository name>/`: `docs/billing.md` becomes `apps/api/billing.md`.
- A listed file goes to the root by its name: `README.md` becomes `apps/api/README.md`, the folder's page.
- Markdown files and images (`png`, `jpg`, `gif`, `svg`, `webp`) up to 1 MB each are synced, up to 500 per repository. Hidden files and symbolic links are skipped.
- Each synced page gets a `source` field, such as `source: "acme/api:docs/billing.md"`. The website's edit link and coding assistants' proposals go to that file.
- A hand edit under `apps/` in the docs repository is overwritten by the next sync. Edit synced pages in their code repository.
- When two entries land on the same path, the first one in the list wins. Absolute paths and paths with `..` are ignored.
- If `.ohara.yml` isn't valid YAML, or isn't a mapping, Ohara keeps the last synced copy and logs the error.
- When the docs repository's default branch is protected, Ohara opens an `ohara/sync-<repository name>` pull request instead. Merge it as is.

### Private code

Synced docs follow the docs repository's access: everyone who can read it can read them. Ohara never syncs a private code repository into a public docs repository. When a private docs repository is made public, Ohara removes the folders of private code repositories, but their files stay in the docs repository's git history.
