"""OAuth for MCP clients: Ohara is the authorization server, GitHub sign-in proves who the user is.

An MCP client registers itself, sends the user to /authorize, and the user signs in with
GitHub. Ohara then issues its own short-lived tokens. Each grant is backed by its own
sign-in session, so the GitHub user token stays on the server and repository access is
re-checked like on the website. Clients and tokens are saved in the data volume.
"""

import hashlib
import json
import secrets
import time
from urllib.parse import urlencode

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    AuthorizeError,
    RefreshToken,
    TokenError,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

from ohara import config, sessions, store

ACCESS_TTL = 3600
REFRESH_TTL = 30 * 24 * 3600
PENDING_TTL = 600
MAX_CLIENTS = 1000  # registration is open to anyone, so keep only the newest clients
PREFIX = "oha_"  # tells Ohara tokens apart from GitHub tokens, so they are never sent to GitHub


class Code(AuthorizationCode):
    session: str


class Refresh(RefreshToken):
    session: str


class Access(AccessToken):
    session: str


def resource_url() -> str:
    return f"{config.base_url()}/mcp"


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _path():
    return config.data_dir() / "oauth.json"


def _load() -> dict:
    try:
        saved = json.loads(_path().read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        saved = {}
    return {"clients": {}, "access": {}, "refresh": {}} | saved


def _save(data: dict) -> None:
    now = time.time()
    for kind in ("access", "refresh"):
        data[kind] = {key: token for key, token in data[kind].items() if token["expires_at"] > now}
    data["clients"] = dict(list(data["clients"].items())[-MAX_CLIENTS:])
    store.write_private(_path(), data)


# Authorization requests waiting for GitHub sign-in, and codes waiting for exchange. Both live minutes.
pending: dict[str, tuple[str, AuthorizationParams, float]] = {}
codes: dict[str, Code] = {}


def _issue(data: dict, client_id: str, session: str, resource: str | None) -> OAuthToken:
    access, refresh = PREFIX + secrets.token_urlsafe(32), PREFIX + secrets.token_urlsafe(32)
    now = int(time.time())
    grant = {"client_id": client_id, "session": session, "resource": resource, "scopes": []}
    data["access"][_hash(access)] = grant | {"expires_at": now + ACCESS_TTL}
    data["refresh"][_hash(refresh)] = grant | {"expires_at": now + REFRESH_TTL}
    _save(data)
    return OAuthToken(access_token=access, token_type="Bearer", expires_in=ACCESS_TTL, refresh_token=refresh)


def _revoke_session(data: dict, session: str) -> None:
    for kind in ("access", "refresh"):
        data[kind] = {key: token for key, token in data[kind].items() if token["session"] != session}
    _save(data)
    sessions.drop(session)


class Provider:
    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        client = _load()["clients"].get(client_id)
        return OAuthClientInformationFull.model_validate(client) if client else None

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        data = _load()
        data["clients"][client_info.client_id] = client_info.model_dump(mode="json", exclude_none=True)
        _save(data)

    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        if params.resource and params.resource.rstrip("/") != resource_url():
            raise AuthorizeError("invalid_request", "Unknown resource")
        now = time.time()
        for key in [key for key, (_, _, at) in pending.items() if now - at > PENDING_TTL]:
            pending.pop(key, None)
        request = secrets.token_urlsafe(24)
        pending[request] = (client.client_id, params, now)
        return f"{config.base_url()}/api/auth/login?{urlencode({'mcp': request})}"

    async def load_authorization_code(self, client: OAuthClientInformationFull, authorization_code: str) -> Code | None:
        code = codes.get(authorization_code)
        return code if code and code.client_id == client.client_id else None

    async def exchange_authorization_code(self, client: OAuthClientInformationFull, authorization_code: Code) -> OAuthToken:
        codes.pop(authorization_code.code, None)
        return _issue(_load(), client.client_id, authorization_code.session, authorization_code.resource)

    async def load_refresh_token(self, client: OAuthClientInformationFull, refresh_token: str) -> Refresh | None:
        token = _load()["refresh"].get(_hash(refresh_token))
        if not token or token["client_id"] != client.client_id or token["expires_at"] < time.time():
            return None
        return Refresh(token=refresh_token, **token)

    async def exchange_refresh_token(self, client: OAuthClientInformationFull, refresh_token: Refresh, scopes: list[str]) -> OAuthToken:
        data = _load()
        if not data["refresh"].pop(_hash(refresh_token.token), None) or not sessions.exists(refresh_token.session):
            _save(data)
            raise TokenError("invalid_grant", "Sign in again")
        return _issue(data, client.client_id, refresh_token.session, refresh_token.resource)

    async def load_access_token(self, token: str) -> Access | None:
        found = _load()["access"].get(_hash(token))
        if not found or found["expires_at"] < time.time():
            return None
        return Access(token=token, **found)

    async def revoke_token(self, token: Access | Refresh) -> None:
        _revoke_session(_load(), token.session)


provider = Provider()


def complete(request: str, session: str | None, allowed: bool) -> str | None:
    """Finish a pending authorization after GitHub sign-in: the client's redirect URL with a code or an error."""
    found = pending.pop(request, None)
    if not found or time.time() - found[2] > PENDING_TTL:
        return None
    client_id, params, _ = found
    redirect_uri = str(params.redirect_uri)
    if not session or not allowed:
        if session:
            sessions.drop(session)
        return construct_redirect_uri(
            redirect_uri, error="access_denied", error_description="No access to the documentation repository", state=params.state
        )
    for expired in [key for key, code in codes.items() if code.expires_at < time.time()]:
        codes.pop(expired, None)
    code = secrets.token_urlsafe(32)
    codes[code] = Code(
        code=code,
        scopes=params.scopes or [],
        expires_at=time.time() + PENDING_TTL,
        client_id=client_id,
        code_challenge=params.code_challenge,
        redirect_uri=params.redirect_uri,
        redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
        resource=params.resource,
        session=session,
    )
    return construct_redirect_uri(redirect_uri, code=code, state=params.state)
