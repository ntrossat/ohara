"""Which docs files need review, from the docs repository's CODEOWNERS file.

A file with code owners needs a human review. Other files merge with the code branch that proposed them.
Without a CODEOWNERS file, every file needs review.
"""

import re
from pathlib import Path

LOCATIONS = (".github/CODEOWNERS", "CODEOWNERS", "docs/CODEOWNERS")  # GitHub's order: the first found wins

Rules = list[tuple[re.Pattern, bool]]


def _regex(pattern: str) -> re.Pattern:
    """A CODEOWNERS pattern (the gitignore subset GitHub supports) as a regular expression on file paths."""
    anchored = pattern.startswith("/") or "/" in pattern.strip("/")
    body = pattern.strip("/")
    out, i = "", 0
    while i < len(body):
        if body.startswith("**/", i):
            out, i = out + "(?:.*/)?", i + 3
        elif body.startswith("**", i):
            out, i = out + ".*", i + 2
        elif body[i] == "*":
            out, i = out + "[^/]*", i + 1
        elif body[i] == "?":
            out, i = out + "[^/]", i + 1
        else:
            out, i = out + re.escape(body[i]), i + 1
    if pattern.endswith("/"):
        suffix = "/.*"  # a folder: everything in it
    elif pattern.endswith("/*"):
        suffix = ""  # only the files directly in the folder
    else:
        suffix = "(?:/.*)?"  # a file, or a folder and everything in it
    return re.compile(("" if anchored else "(?:.*/)?") + out + suffix)


def parse(text: str) -> Rules:
    """(pattern, has owners) per rule. A rule without owners makes its files unowned again."""
    rules = []
    for line in text.splitlines():
        parts = line.split("#", 1)[0].split()
        if parts:
            rules.append((_regex(parts[0]), len(parts) > 1))
    return rules


def load(root: Path) -> Rules | None:
    """The rules of the docs snapshot's CODEOWNERS file, or None without one."""
    for location in LOCATIONS:
        file = root / location
        if file.is_file():
            return parse(file.read_text(errors="replace"))
    return None


def needs_review(rules: Rules | None, path: str) -> bool:
    """Whether a docs file needs a human review: it has code owners, or there is no CODEOWNERS file. The last
    matching rule wins."""
    if rules is None:
        return True
    owned = False
    for regex, has_owners in rules:
        if regex.fullmatch(path):
            owned = has_owners
    return owned
