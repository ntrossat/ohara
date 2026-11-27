"""Changes to review: the open pull requests of the docs repository, shown on the website.

Readers see them through the installation token, as they see the docs. Approving a change merges its pull
request with the approver's own token, so GitHub applies their rights and the repository's rules.
This module owns the proposal signature, which names who proposed a change through Ohara, and with which agent.
"""

import asyncio
import re
import time

from ohara import docs, github

LIST_TTL = 60  # seconds the list of open pull requests is kept
MAX_PAGES = 30  # pages of one change shown with their text; the rest are only named
AGENT_LENGTH = 40  # characters kept of an agent's name
SIGNATURE = re.compile(r"\s*---\s*Proposed through Ohara by @([\w-]+)(?:, with ([^\n]+?))?\.\s*\Z")

_listed: tuple[float, str, list[dict]] | None = None  # when, for which repository, and the list


def sign(description: str, login: str, agent: str | None = None) -> str:
    """A pull request body that names the user a proposal comes from, as the app opens it, and the agent that
    wrote it. The agent names itself, so only plain characters of its name are kept."""
    agent = re.sub(r"[^\w .()-]+", "", agent or "")[:AGENT_LENGTH].strip(" .")
    return f"{description}\n\n---\nProposed through Ohara by @{login}{f', with {agent}' if agent else ''}."


def summary(pull: dict) -> dict:
    """A pull request as the website shows it: proposed by the user in its signature, not by the app."""
    body = pull.pop("body")
    signed = SIGNATURE.search(body)
    if signed:
        return pull | {"author": signed.group(1), "agent": signed.group(2), "description": body[: signed.start()].strip()}
    return pull | {"agent": None, "description": body.strip()}


async def code_pull(token: str, full_name: str, branch: str, private: bool) -> dict | None:
    """The code pull request a change comes with: the latest one of the code branch its docs branch names
    ("project/branch"), in the docs repository's account. A private code repository is never named on public docs."""
    project, _, code_branch = branch.partition("/")
    if not code_branch:
        return None
    found = await github.latest_pull(token, f"{full_name.split('/')[0]}/{project}", code_branch)
    if not found or found.pop("private") and not private:
        return None
    return found


async def listed(token: str, full_name: str) -> list[dict]:
    """The open pull requests, without their descriptions."""
    global _listed
    if not _listed or _listed[1] != full_name or time.time() - _listed[0] > LIST_TTL:
        pulls = [summary(pull) for pull in await github.open_pulls(token, full_name)]
        _listed = (time.time(), full_name, [{key: pull[key] for key in pull if key != "description"} for pull in pulls])
    return _listed[2]


def forget() -> None:
    """Drop the kept list, after a merge."""
    global _listed
    _listed = None


def status_of(status: str) -> str:
    return {"added": "added", "copied": "added", "removed": "removed"}.get(status, "changed")


async def read(token: str, full_name: str, number: int, private: bool) -> dict | None:
    """A pull request with the pages it changes: each page's text before and after, without front matter.
    Other files, and pages past `MAX_PAGES`, come without text. `code` is the code pull request it comes with."""
    pull = await github.get_pull(token, full_name, number)
    if not pull:
        return None
    head = pull.pop("head")
    base, changed = await github.pull_changes(token, full_name, pull.pop("base"), head)
    shown = [file for file in changed if file["file"].endswith(".md")][:MAX_PAGES]

    async def text(path: str, ref: str) -> str | None:
        found = await github.get_file(token, full_name, path, ref)
        return None if found is None else docs.parse(found)[1]

    async def page(file: dict) -> dict:
        status = status_of(file["status"])
        before, after = await asyncio.gather(
            text(file["previous"], base) if status != "added" else asyncio.sleep(0),
            text(file["file"], head) if status != "removed" else asyncio.sleep(0),
        )
        return {"file": file["file"], "status": status, "before": before, "after": after}

    pages = {file["file"]: file for file in await asyncio.gather(*(page(file) for file in shown))}
    files = [
        pages.get(file["file"]) or {"file": file["file"], "status": status_of(file["status"]), "before": None, "after": None}
        for file in changed
    ]
    found = summary(pull)
    return found | {"sha": head, "files": files, "code": await code_pull(token, full_name, found["branch"], private)}
