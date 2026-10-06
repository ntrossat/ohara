"""OAuth for MCP clients: Ohara is the authorization server, GitHub sign-in proves who the user is.

An MCP client registers itself, sends the user to /authorize, and the user signs in with
GitHub, then approves the client on Ohara's consent page. Ohara then issues its own short-lived tokens. Each grant is backed by its own
sign-in session, so the GitHub user token stays on the server and repository access is
re-checked like on the website. Clients, tokens, and pending sign-ins are saved in the database.
"""

import hashlib
import secrets
import time
from urllib.parse import urlencode, urlparse

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

from ohara import config, db, sessions

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


def _issue(client_id: str, session: str, resource: str | None) -> OAuthToken:
    access, refresh = PREFIX + secrets.token_urlsafe(32), PREFIX + secrets.token_urlsafe(32)
    now = int(time.time())
    grant = {"client_id": client_id, "session": session, "resource": resource, "scopes": []}
    with db.connect() as conn:
        db.put("access", _hash(access), grant | {"expires_at": now + ACCESS_TTL}, now + ACCESS_TTL, conn=conn)
        db.put("refresh", _hash(refresh), grant | {"expires_at": now + REFRESH_TTL}, now + REFRESH_TTL, conn=conn)
    return OAuthToken(access_token=access, token_type="Bearer", expires_in=ACCESS_TTL, refresh_token=refresh)


class Provider:
    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        client = db.get("client", client_id)
        return OAuthClientInformationFull.model_validate(client) if client else None

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        db.put("client", client_info.client_id, client_info.model_dump(mode="json", exclude_none=True))
        db.keep_newest("client", MAX_CLIENTS)

    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        if params.resource and params.resource.rstrip("/") != resource_url():
            raise AuthorizeError("invalid_request", "Unknown resource")
        request = secrets.token_urlsafe(24)
        pending = {"client_id": client.client_id, "params": params.model_dump(mode="json")}
        db.put("pending", request, pending, time.time() + PENDING_TTL)
        return f"{config.base_url()}/api/auth/login?{urlencode({'mcp': request})}"

    async def load_authorization_code(self, client: OAuthClientInformationFull, authorization_code: str) -> Code | None:
        code = db.get("code", authorization_code)
        return Code.model_validate(code) if code and code["client_id"] == client.client_id else None

    async def exchange_authorization_code(self, client: OAuthClientInformationFull, authorization_code: Code) -> OAuthToken:
        if not db.pop("code", authorization_code.code):
            raise TokenError("invalid_grant", "Authorization code already used")
        return _issue(client.client_id, authorization_code.session, authorization_code.resource)

    async def load_refresh_token(self, client: OAuthClientInformationFull, refresh_token: str) -> Refresh | None:
        token = db.get("refresh", _hash(refresh_token))
        if not token or token["client_id"] != client.client_id:
            return None
        return Refresh(token=refresh_token, **token)

    async def exchange_refresh_token(self, client: OAuthClientInformationFull, refresh_token: Refresh, scopes: list[str]) -> OAuthToken:
        if not db.pop("refresh", _hash(refresh_token.token)) or not sessions.exists(refresh_token.session):
            raise TokenError("invalid_grant", "Sign in again")
        return _issue(client.client_id, refresh_token.session, refresh_token.resource)

    async def load_access_token(self, token: str) -> Access | None:
        found = db.get("access", _hash(token))
        return Access(token=token, **found) if found else None

    async def revoke_token(self, token: Access | Refresh) -> None:
        db.delete_where(("access", "refresh"), "session", token.session)
        sessions.drop(token.session)


provider = Provider()


def describe(request: str) -> dict | None:
    """What the consent page shows: the client's name and where it sends the user back."""
    found = db.get("pending", request)
    client = found and db.get("client", found["client_id"])
    if not client:
        return None
    redirect = urlparse(found["params"]["redirect_uri"])
    return {"client": client.get("client_name") or "An unnamed app", "redirect": f"{redirect.scheme}://{redirect.netloc}"}


def complete(request: str, session: str | None, denied: str | None = None) -> str | None:
    """Finish a pending authorization: the client's redirect URL with a code, or with an error when `denied`."""
    found = db.pop("pending", request)
    if not found:
        return None
    params = AuthorizationParams.model_validate(found["params"])
    redirect_uri = str(params.redirect_uri)
    if not session or denied:
        if session:
            sessions.drop(session)
        return construct_redirect_uri(redirect_uri, error="access_denied", error_description=denied, state=params.state)
    code = secrets.token_urlsafe(32)
    expires_at = time.time() + PENDING_TTL
    granted = Code(
        code=code,
        scopes=params.scopes or [],
        expires_at=expires_at,
        client_id=found["client_id"],
        code_challenge=params.code_challenge,
        redirect_uri=params.redirect_uri,
        redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
        resource=params.resource,
        session=session,
    )
    db.put("code", code, granted.model_dump(mode="json"), expires_at)
    return construct_redirect_uri(redirect_uri, code=code, state=params.state)
