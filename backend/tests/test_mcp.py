import base64
import datetime
import hashlib
import json
import pathlib
from urllib.parse import parse_qs, urlparse

import httpx
import respx

from ohara import docs, mcp_server, oauth, sessions
from tests.conftest import REPO

REPO_URL = f"https://api.github.com/repos/{REPO}"
HEADERS = {"Accept": "application/json, text/event-stream", "MCP-Protocol-Version": "2025-06-18"}


def call(client, tool, token=None, **arguments):
    headers = HEADERS | ({"Authorization": f"Bearer {token}"} if token else {})
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": tool, "arguments": arguments}}
    return client.post("/mcp", json=body, headers=headers)


def result(response):
    assert response.status_code == 200, response.text
    return response.json()["result"]


def test_public_repository_is_open_without_a_token(mcp, configure):
    configure(private=False)
    assert result(call(mcp, "read_page", path="guide"))["structuredContent"]["markdown"] == "# Guide"


def test_lists_pages_with_their_folders(mcp, configure, data_dir):
    configure(private=False)
    (data_dir / "docs" / "team").mkdir()
    (data_dir / "docs" / "team" / "onboarding.md").write_text("# Onboarding")
    pages = result(call(mcp, "list_pages"))["structuredContent"]["result"]
    assert {"path": "guide", "title": "Guide"} in pages
    assert {"path": "team/onboarding", "title": "Team / Onboarding"} in pages


def test_search_matches_every_word(mcp, configure, data_dir):
    configure(private=False)
    (data_dir / "docs" / "deploy.md").write_text("# Deploy\n\nShip with blue green releases.")
    docs.index(data_dir / "docs")
    found = result(call(mcp, "search", query="green DEPLOY"))["structuredContent"]["result"]
    assert found == [{"path": "deploy", "title": "Deploy", "snippet": "Ship with blue green releases.", "stale": []}]
    assert result(call(mcp, "search", query="red"))["structuredContent"]["result"] == []


def test_missing_page_is_a_tool_error(mcp, configure):
    configure(private=False)
    found = result(call(mcp, "read_page", path="nope"))
    assert found["isError"] is True
    assert "Page not found: nope" in found["content"][0]["text"]


def test_private_repository_requires_a_token(mcp, configure):
    configure(private=True)
    response = call(mcp, "list_pages")
    assert response.status_code == 401
    metadata = "https://docs.example.com/.well-known/oauth-protected-resource/mcp"
    assert response.headers["WWW-Authenticate"] == f'Bearer resource_metadata="{metadata}"'


@respx.mock
def test_token_with_repository_access_can_read(mcp, configure):
    configure(private=True)
    route = respx.get(REPO_URL).mock(return_value=httpx.Response(200, json={}))
    assert result(call(mcp, "read_page", token="ghp_1", path="guide"))["structuredContent"]["markdown"] == "# Guide"
    result(call(mcp, "read_page", token="ghp_1", path="guide"))
    assert route.call_count == 1  # re-checked every 5 minutes, not on each call


@respx.mock
def test_token_without_repository_access_is_rejected(mcp, configure):
    configure(private=True)
    respx.get(REPO_URL).mock(return_value=httpx.Response(404))
    assert call(mcp, "list_pages", token="ghp_1").status_code == 403


@respx.mock
def test_invalid_token_is_rejected(mcp, configure):
    configure(private=True)
    respx.get(REPO_URL).mock(return_value=httpx.Response(401))
    assert call(mcp, "list_pages", token="bad").status_code == 401


# OAuth sign-in for MCP clients

REDIRECT = "http://localhost:33418/callback"
VERIFIER = "v" * 64
CHALLENGE = base64.urlsafe_b64encode(hashlib.sha256(VERIFIER.encode()).digest()).decode().rstrip("=")


def query(url):
    return {key: values[0] for key, values in parse_qs(urlparse(url).query).items()}


def mock_github_sign_in(repo_status=200):
    respx.post("https://github.com/login/oauth/access_token").mock(
        return_value=httpx.Response(200, json={"access_token": "ghu_1", "refresh_token": "ghr_1", "expires_in": 28800})
    )
    respx.get("https://api.github.com/user").mock(return_value=httpx.Response(200, json={"login": "ada"}))
    return respx.get(REPO_URL).mock(return_value=httpx.Response(repo_status, json={}))


def authorize(client, approve=True):
    """Run discovery, registration, the browser sign-in, and the consent page. Returns the client id and the final redirect."""
    resource = client.get("/.well-known/oauth-protected-resource/mcp").json()
    assert resource["authorization_servers"] == ["https://docs.example.com"]
    server = client.get("/.well-known/oauth-authorization-server").json()
    registered = client.post(
        urlparse(server["registration_endpoint"]).path,
        json={"redirect_uris": [REDIRECT], "token_endpoint_auth_method": "none", "client_name": "Claude Code"},
    ).json()
    params = {
        "response_type": "code",
        "client_id": registered["client_id"],
        "redirect_uri": REDIRECT,
        "code_challenge": CHALLENGE,
        "code_challenge_method": "S256",
        "state": "client-state",
        "resource": "https://docs.example.com/mcp",
    }
    login = client.get("/authorize", params=params).headers["location"]
    github = client.get(urlparse(login).path + "?" + urlparse(login).query).headers["location"]
    done = client.get("/api/auth/callback", params={"code": "gh-code", "state": query(github)["state"]})
    assert done.status_code == 303
    if done.headers["location"] != "/oauth/consent":
        return registered["client_id"], done.headers["location"]
    assert client.get("/api/auth/consent").json() == {"client": "Claude Code", "redirect": "http://localhost:33418", "login": "ada"}
    answered = client.post("/api/auth/consent", json={"approve": approve})
    assert answered.status_code == 200
    return registered["client_id"], answered.json()["redirect"]


def token(client, **form):
    return client.post("/token", data=form)


@respx.mock
def test_mcp_client_signs_in_with_github(mcp, configure):
    configure(private=True)
    mock_github_sign_in()
    client_id, redirect = authorize(mcp)
    assert redirect.startswith(REDIRECT)
    assert query(redirect)["state"] == "client-state"
    assert "ohara_session" not in mcp.cookies  # no website session from an MCP sign-in

    tokens = token(
        mcp,
        grant_type="authorization_code",
        code=query(redirect)["code"],
        redirect_uri=REDIRECT,
        client_id=client_id,
        code_verifier=VERIFIER,
        resource="https://docs.example.com/mcp",
    ).json()
    assert tokens["expires_in"] == 3600
    assert result(call(mcp, "read_page", token=tokens["access_token"], path="guide"))["structuredContent"]["markdown"] == "# Guide"

    refreshed = token(mcp, grant_type="refresh_token", refresh_token=tokens["refresh_token"], client_id=client_id).json()
    assert result(call(mcp, "list_pages", token=refreshed["access_token"]))
    reused = token(mcp, grant_type="refresh_token", refresh_token=tokens["refresh_token"], client_id=client_id)
    assert reused.status_code == 400  # refresh tokens rotate

    # The SDK's revocation form requires client_secret, even empty for public clients.
    mcp.post("/revoke", data={"token": refreshed["access_token"], "client_id": client_id, "client_secret": ""})
    assert call(mcp, "list_pages", token=refreshed["access_token"]).status_code == 401


@respx.mock
def test_mcp_sign_in_is_denied_without_repository_access(mcp, configure):
    configure(private=True)
    mock_github_sign_in(repo_status=404)
    _, redirect = authorize(mcp)
    assert query(redirect)["error"] == "access_denied"
    assert "code" not in query(redirect)


@respx.mock
def test_mcp_sign_in_can_be_cancelled(mcp, configure):
    configure(private=True)
    mock_github_sign_in()
    _, redirect = authorize(mcp, approve=False)
    assert query(redirect)["error"] == "access_denied"
    assert "code" not in query(redirect)


@respx.mock
def test_consent_only_works_in_the_browser_that_signed_in(mcp, configure):
    configure(private=True)
    mock_github_sign_in()
    registered = mcp.post("/register", json={"redirect_uris": [REDIRECT], "token_endpoint_auth_method": "none"}).json()
    login = mcp.get("/authorize", params={
        "response_type": "code", "client_id": registered["client_id"], "redirect_uri": REDIRECT,
        "code_challenge": CHALLENGE, "code_challenge_method": "S256",
    }).headers["location"]
    github = mcp.get(urlparse(login).path + "?" + urlparse(login).query).headers["location"]
    mcp.get("/api/auth/callback", params={"code": "gh-code", "state": query(github)["state"]})
    consent = mcp.cookies.pop("ohara_consent")
    assert mcp.post("/api/auth/consent", json={"approve": True}).status_code == 404
    mcp.cookies.set("ohara_consent", consent)
    assert mcp.post("/api/auth/consent", json={"approve": True}).status_code == 200
    assert mcp.post("/api/auth/consent", json={"approve": True}).status_code == 404  # one answer only


@respx.mock
def test_mcp_token_loses_access_with_the_repository(mcp, configure, monkeypatch):
    configure(private=True)
    repo = mock_github_sign_in()
    client_id, redirect = authorize(mcp)
    tokens = token(
        mcp, grant_type="authorization_code", code=query(redirect)["code"], redirect_uri=REDIRECT,
        client_id=client_id, code_verifier=VERIFIER,
    ).json()
    repo.mock(return_value=httpx.Response(404))
    monkeypatch.setattr(sessions, "CHECK_INTERVAL", 0)
    assert call(mcp, "list_pages", token=tokens["access_token"]).status_code == 403


def test_authorization_code_needs_the_pkce_verifier(mcp, configure):
    configure(private=True)
    with respx.mock:
        mock_github_sign_in()
        client_id, redirect = authorize(mcp)
    denied = token(
        mcp, grant_type="authorization_code", code=query(redirect)["code"], redirect_uri=REDIRECT,
        client_id=client_id, code_verifier="w" * 64,
    )
    assert denied.status_code == 400


def test_client_registrations_are_capped(mcp, configure, monkeypatch):
    configure(private=True)
    monkeypatch.setattr(oauth, "MAX_CLIENTS", 2)
    ids = [mcp.post("/register", json={"redirect_uris": [REDIRECT], "token_endpoint_auth_method": "none"}).json()["client_id"] for _ in range(3)]
    params = {"response_type": "code", "redirect_uri": REDIRECT, "code_challenge": CHALLENGE, "code_challenge_method": "S256"}
    assert mcp.get("/authorize", params=params | {"client_id": ids[0]}).status_code == 400
    assert mcp.get("/authorize", params=params | {"client_id": ids[2]}).status_code == 302


def test_search_ranks_title_matches_first_and_accepts_any_text(mcp, configure, data_dir):
    configure(private=False)
    (data_dir / "docs" / "testing.md").write_text("# Testing\n\nRun the suite before you deploy.")
    (data_dir / "docs" / "deploy.md").write_text("# Deploy\n\nDeploys go out after tests pass.")
    docs.index(data_dir / "docs")
    found = result(call(mcp, "search", query="deploy"))["structuredContent"]["result"]
    assert [page["path"] for page in found] == ["deploy", "testing"]
    assert result(call(mcp, "search", query='"blue-green" OR * :'))["structuredContent"]["result"] == []


# Change proposals

API = "https://api.github.com"
PROPOSAL = {
    "title": "Document the deploy freeze",
    "description": "Deploys stop on Fridays.",
    "pages": [{"path": "guide", "markdown": "# Guide\n\nNo deploys on Fridays."}, {"path": "team/oncall", "markdown": "# On call"}],
}


def mock_proposal(push=True):
    respx.get(REPO_URL).mock(return_value=httpx.Response(200, json={"permissions": {"push": push}}))
    respx.get(f"{API}/user").mock(return_value=httpx.Response(200, json={"login": "ada"}))
    respx.post(f"{API}/app/installations/42/access_tokens").mock(return_value=httpx.Response(201, json={"token": "ghs_app"}))
    respx.get(f"{REPO_URL}/pulls").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{REPO_URL}/git/ref/heads/main").mock(return_value=httpx.Response(200, json={"object": {"sha": "base-sha"}}))
    ref = respx.post(f"{REPO_URL}/git/refs").mock(return_value=httpx.Response(201, json={}))
    respx.get(f"{REPO_URL}/contents/guide.md").mock(return_value=httpx.Response(200, json={"sha": "guide-sha"}))
    respx.get(f"{REPO_URL}/contents/team/oncall.md").mock(return_value=httpx.Response(404))
    put_guide = respx.put(f"{REPO_URL}/contents/guide.md").mock(return_value=httpx.Response(200, json={}))
    put_new = respx.put(f"{REPO_URL}/contents/team/oncall.md").mock(return_value=httpx.Response(201, json={}))
    pull = respx.post(f"{REPO_URL}/pulls").mock(return_value=httpx.Response(201, json={"html_url": "https://github.com/acme/handbook/pull/7"}))
    return ref, put_guide, put_new, pull


@respx.mock
def test_proposal_opens_a_pull_request_from_the_app(mcp, configure):
    configure(private=False)
    ref, put_guide, put_new, pull = mock_proposal()
    answer = result(call(mcp, "propose_change", token="ghp_1", **PROPOSAL))
    assert answer["structuredContent"]["result"] == "https://github.com/acme/handbook/pull/7"

    branch = json.loads(ref.calls.last.request.content)
    assert branch["ref"].startswith("refs/heads/ohara/document-the-deploy-freeze-") and branch["sha"] == "base-sha"
    assert ref.calls.last.request.headers["Authorization"] == "Bearer ghs_app"  # the app opens it, so the user can approve
    guide = json.loads(put_guide.calls.last.request.content)
    today = datetime.date.today().isoformat()
    assert base64.b64decode(guide["content"]).decode() == f"---\nverified: {today}\n---\n\n# Guide\n\nNo deploys on Fridays."
    assert guide["sha"] == "guide-sha"
    assert "sha" not in json.loads(put_new.calls.last.request.content)
    opened = json.loads(pull.calls.last.request.content)
    assert opened["base"] == "main" and opened["head"] == branch["ref"].removeprefix("refs/heads/")
    assert opened["body"] == "Deploys stop on Fridays.\n\n---\nProposed through Ohara by @ada."


@respx.mock
def test_proposal_from_a_code_branch_uses_a_project_branch(mcp, configure):
    configure(private=False)
    ref, _, _, pull = mock_proposal()
    find = respx.get(f"{REPO_URL}/pulls").mock(return_value=httpx.Response(200, json=[]))
    answer = result(call(mcp, "propose_change", token="ghp_1", project="api", branch="feature/new billing", **PROPOSAL))
    assert answer["structuredContent"]["result"].endswith("/pull/7")
    assert find.calls.last.request.url.params["head"] == "acme:api/feature/new-billing"
    assert json.loads(ref.calls.last.request.content)["ref"] == "refs/heads/api/feature/new-billing"
    assert json.loads(pull.calls.last.request.content)["head"] == "api/feature/new-billing"


@respx.mock
def test_proposal_adds_to_the_open_pull_request_of_its_branch(mcp, configure):
    configure(private=False)
    ref, put_guide, _, pull = mock_proposal()
    respx.get(f"{REPO_URL}/pulls").mock(
        return_value=httpx.Response(200, json=[{"number": 5, "html_url": "https://github.com/acme/handbook/pull/5"}])
    )
    comment = respx.post(f"{REPO_URL}/issues/5/comments").mock(return_value=httpx.Response(201, json={}))
    answer = result(call(mcp, "propose_change", token="ghp_1", project="api", branch="main", **PROPOSAL))
    assert answer["structuredContent"]["result"] == "https://github.com/acme/handbook/pull/5"
    assert json.loads(put_guide.calls.last.request.content)["branch"] == "api/main"
    assert "Document the deploy freeze" in json.loads(comment.calls.last.request.content)["body"]
    assert not ref.called and not pull.called


@respx.mock
def test_proposal_restarts_a_branch_left_from_a_closed_pull_request(mcp, configure):
    configure(private=False)
    ref, _, _, pull = mock_proposal()
    ref.mock(return_value=httpx.Response(422, json={}))
    reset = respx.patch(f"{REPO_URL}/git/refs/heads/api/main").mock(return_value=httpx.Response(200, json={}))
    assert result(call(mcp, "propose_change", token="ghp_1", project="api", branch="main", **PROPOSAL))["structuredContent"]["result"].endswith("/pull/7")
    assert json.loads(reset.calls.last.request.content) == {"sha": "base-sha", "force": True}
    assert pull.called


def test_proposal_requires_a_signed_in_caller(mcp, configure):
    configure(private=False)
    assert result(call(mcp, "propose_change", **PROPOSAL))["isError"] is True


@respx.mock
def test_proposal_requires_write_access(mcp, configure):
    configure(private=False)
    _, _, _, pull = mock_proposal(push=False)
    assert result(call(mcp, "propose_change", token="ghp_1", **PROPOSAL))["isError"] is True
    assert not pull.called


@respx.mock
def test_proposal_rejects_paths_outside_the_docs(mcp, configure):
    configure(private=False)
    _, _, _, pull = mock_proposal()
    for path in ("../secrets", "team/../../x", ".github/workflows/deploy"):
        proposal = PROPOSAL | {"pages": [{"path": path, "markdown": "x"}]}
        assert result(call(mcp, "propose_change", token="ghp_1", **proposal))["isError"] is True, path
    assert not pull.called


@respx.mock
def test_proposal_checks_collaborator_permission_when_the_repository_omits_it(mcp, configure):
    configure(private=False)
    mock_proposal()
    respx.get(REPO_URL).mock(return_value=httpx.Response(200, json={}))
    permission = respx.get(f"{REPO_URL}/collaborators/ada/permission").mock(return_value=httpx.Response(200, json={"permission": "read"}))
    assert result(call(mcp, "propose_change", token="ghp_1", **PROPOSAL))["isError"] is True
    permission.mock(return_value=httpx.Response(200, json={"permission": "write"}))
    assert result(call(mcp, "propose_change", token="ghp_1", **PROPOSAL))["structuredContent"]["result"].endswith("/pull/7")


def rpc(client, method, **params):
    body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    return client.post("/mcp", json=body, headers=HEADERS)


def test_init_prompt_sets_up_a_project(mcp, configure):
    configure(private=False)
    assert "init" in [prompt["name"] for prompt in result(rpc(mcp, "prompts/list"))["prompts"]]
    text = result(rpc(mcp, "prompts/get", name="init"))["messages"][0]["content"]["text"]
    assert '"url": "https://docs.example.com/mcp"' in text
    assert REPO in text
    assert ".claude/hooks/ohara-check.sh" in text


def test_init_prompt_hook_matches_the_project_hook():
    hook = pathlib.Path(__file__).parents[2] / ".claude/hooks/ohara-check.sh"
    assert hook.read_text() in mcp_server.INIT_PROMPT


def test_init_prompt_requires_access(mcp, configure):
    configure(private=True)
    assert rpc(mcp, "prompts/get", name="init").status_code == 401


def test_update_prompt_proposes_documentation_changes(mcp, configure):
    configure(private=False)
    text = result(rpc(mcp, "prompts/get", name="update"))["messages"][0]["content"]["text"]
    assert "https://docs.example.com" in text and REPO in text
    assert "propose_change" in text


def test_prompts_cover_the_project_commands(mcp, configure):
    configure(private=False)
    assert [prompt["name"] for prompt in result(rpc(mcp, "prompts/list"))["prompts"]] == ["init", "update", "review", "ingest"]
    text = result(rpc(mcp, "prompts/get", name="review"))["messages"][0]["content"]["text"]
    assert REPO in text and "file:line" in text


def test_ingest_prompt_treats_sources_as_untrusted(mcp, configure):
    configure(private=False)
    text = result(rpc(mcp, "prompts/get", name="ingest"))["messages"][0]["content"]["text"]
    assert REPO in text and "untrusted" in text and "propose_change" in text
