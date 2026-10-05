"""Signed-in users, saved in the data volume so they survive restarts.
A user's repository access is re-checked with GitHub every 5 minutes."""

import json
import secrets
import time
from dataclasses import asdict, dataclass

from ohara import github, store
from ohara.config import data_dir

CHECK_INTERVAL = 300


@dataclass
class Session:
    login: str
    avatar: str
    token: str
    refresh: str | None
    expires_at: float | None
    allowed: bool = False
    checked_at: float = 0.0


sessions: dict[str, Session] = {}
_loaded = False


def _path():
    return data_dir() / "sessions.json"


def _load() -> None:
    global _loaded
    if _loaded:
        return
    _loaded = True
    try:
        saved = json.loads(_path().read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return
    sessions.update({sid: Session(**values) for sid, values in saved.items()})


def _save() -> None:
    store.write_private(_path(), {sid: asdict(session) for sid, session in sessions.items()})


def _expires_at(tokens: dict) -> float | None:
    return time.time() + tokens["expires_in"] if tokens.get("expires_in") else None


def create(tokens: dict, user: dict) -> str:
    _load()
    sid = secrets.token_urlsafe(32)
    sessions[sid] = Session(
        login=user["login"],
        avatar=user.get("avatar_url", ""),
        token=tokens["access_token"],
        refresh=tokens.get("refresh_token"),
        expires_at=_expires_at(tokens),
    )
    _save()
    return sid


def exists(sid: str) -> bool:
    _load()
    return sid in sessions


def drop(sid: str | None) -> None:
    _load()
    if sessions.pop(sid, None):
        _save()


async def _refresh(app: dict, session: Session) -> bool:
    if not session.refresh:
        return False
    try:
        tokens = await github.refresh_token(app, session.refresh)
    except github.Unauthorized:
        return False
    session.token = tokens["access_token"]
    session.refresh = tokens.get("refresh_token", session.refresh)
    session.expires_at = _expires_at(tokens)
    _save()
    return True


async def current(sid: str | None, app: dict, repo: str) -> Session | None:
    """Return the session with an up-to-date `allowed` flag, or None when the user must sign in again."""
    _load()
    session = sessions.get(sid) if sid else None
    if not session:
        return None
    now = time.time()
    if now - session.checked_at < CHECK_INTERVAL:
        return session
    if session.expires_at and now > session.expires_at - 60 and not await _refresh(app, session):
        drop(sid)
        return None
    try:
        try:
            session.allowed = await github.user_can_read(session.token, repo)
        except github.Unauthorized:
            if not await _refresh(app, session):
                raise
            session.allowed = await github.user_can_read(session.token, repo)
    except github.Unauthorized:
        drop(sid)
        return None
    session.checked_at = now
    return session
