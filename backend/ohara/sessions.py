"""Signed-in users, saved in the database so they survive restarts.
A user's repository access is re-checked with GitHub every 5 minutes.
A session ends after 30 days without use."""

import secrets
import time
from dataclasses import asdict, dataclass

from ohara import db, github

CHECK_INTERVAL = 300
TTL = 30 * 24 * 3600


@dataclass
class Session:
    login: str
    avatar: str
    token: str
    refresh: str | None
    expires_at: float | None
    allowed: bool = False
    checked_at: float = 0.0


def get(sid: str | None) -> Session | None:
    values = db.get("session", sid) if sid else None
    return Session(**values) if values else None


def save(sid: str, session: Session) -> None:
    db.put("session", sid, asdict(session), time.time() + TTL)


def _expires_at(tokens: dict) -> float | None:
    return time.time() + tokens["expires_in"] if tokens.get("expires_in") else None


def create(tokens: dict, user: dict) -> str:
    sid = secrets.token_urlsafe(32)
    save(
        sid,
        Session(
            login=user["login"],
            avatar=user.get("avatar_url", ""),
            token=tokens["access_token"],
            refresh=tokens.get("refresh_token"),
            expires_at=_expires_at(tokens),
        ),
    )
    return sid


def exists(sid: str) -> bool:
    return get(sid) is not None


def drop(sid: str | None) -> None:
    if sid:
        db.delete("session", sid)


async def _refresh(app: dict, sid: str, session: Session) -> bool:
    if not session.refresh:
        return False
    try:
        tokens = await github.refresh_token(app, session.refresh)
    except github.Unauthorized:
        return False
    session.token = tokens["access_token"]
    session.refresh = tokens.get("refresh_token", session.refresh)
    session.expires_at = _expires_at(tokens)
    save(sid, session)
    return True


async def current(sid: str | None, app: dict, repo: str) -> Session | None:
    """Return the session with an up-to-date `allowed` flag, or None when the user must sign in again."""
    session = get(sid)
    if not session:
        return None
    now = time.time()
    if now - session.checked_at < CHECK_INTERVAL:
        return session
    if session.expires_at and now > session.expires_at - 60 and not await _refresh(app, sid, session):
        drop(sid)
        return None
    try:
        try:
            session.allowed = await github.user_can_read(session.token, repo)
        except github.Unauthorized:
            if not await _refresh(app, sid, session):
                raise
            session.allowed = await github.user_can_read(session.token, repo)
    except github.Unauthorized:
        drop(sid)
        return None
    session.checked_at = now
    save(sid, session)
    return session
