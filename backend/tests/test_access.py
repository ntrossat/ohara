import time

import httpx
import respx

from ohara import sessions
from tests.conftest import REPO

REPO_URL = f"https://api.github.com/repos/{REPO}"


def sign_in(token="ghu_1", refresh="ghr_1", expires_in=28800):
    return sessions.create(
        {"access_token": token, "refresh_token": refresh, "expires_in": expires_in},
        {"login": "ada", "avatar_url": "https://avatars/ada"},
    )


@respx.mock
def test_sessions_survive_a_restart(client, configure):
    configure(private=True)
    respx.get(REPO_URL).mock(return_value=httpx.Response(200, json={}))
    client.cookies.set("ohara_session", sign_in())
    assert client.get("/api/status").json()["user"]["login"] == "ada"


def test_public_repository_is_open_without_sign_in(client, configure):
    configure(private=False)
    assert client.get("/api/page", params={"path": "guide"}).json()["title"] == "Guide"
    status = client.get("/api/status").json()
    assert status["allowed"] is True
    assert status["branch"] == "main"


def test_private_repository_requires_sign_in(client, configure):
    configure(private=True)
    assert client.get("/api/nav").status_code == 401
    assert client.get("/api/files/guide.md").status_code == 401


@respx.mock
def test_user_with_repository_access_can_read(client, configure):
    configure(private=True)
    respx.get(REPO_URL).mock(return_value=httpx.Response(200, json={}))
    client.cookies.set("ohara_session", sign_in())
    assert client.get("/api/page", params={"path": "guide"}).status_code == 200
    assert client.get("/api/status").json()["user"]["login"] == "ada"


@respx.mock
def test_user_without_repository_access_is_refused(client, configure):
    configure(private=True)
    respx.get(REPO_URL).mock(return_value=httpx.Response(404))
    client.cookies.set("ohara_session", sign_in())
    assert client.get("/api/nav").status_code == 403


@respx.mock
def test_access_is_cached_for_five_minutes_then_rechecked(client, configure):
    configure(private=True)
    route = respx.get(REPO_URL).mock(return_value=httpx.Response(200, json={}))
    sid = sign_in()
    client.cookies.set("ohara_session", sid)
    client.get("/api/nav")
    client.get("/api/nav")
    assert route.call_count == 1

    route.mock(return_value=httpx.Response(404))
    session = sessions.get(sid)
    session.checked_at = time.time() - sessions.CHECK_INTERVAL - 1
    sessions.save(sid, session)
    assert client.get("/api/nav").status_code == 403
    assert route.call_count == 2


@respx.mock
def test_expired_token_is_refreshed(client, configure):
    configure(private=True)
    respx.post("https://github.com/login/oauth/access_token").mock(
        return_value=httpx.Response(200, json={"access_token": "ghu_2", "refresh_token": "ghr_2", "expires_in": 28800})
    )
    repo = respx.get(REPO_URL).mock(return_value=httpx.Response(200, json={}))
    sid = sign_in(expires_in=1)
    client.cookies.set("ohara_session", sid)
    assert client.get("/api/nav").status_code == 200
    assert repo.calls.last.request.headers["Authorization"] == "Bearer ghu_2"


@respx.mock
def test_revoked_token_ends_the_session(client, configure):
    configure(private=True)
    respx.get(REPO_URL).mock(return_value=httpx.Response(401))
    respx.post("https://github.com/login/oauth/access_token").mock(
        return_value=httpx.Response(200, json={"error": "bad_refresh_token"})
    )
    sid = sign_in()
    client.cookies.set("ohara_session", sid)
    assert client.get("/api/nav").status_code == 401
    assert not sessions.exists(sid)


@respx.mock
def test_sign_in_flow_creates_session_and_returns_to_page(client, configure):
    configure(private=True)
    login = client.get("/api/auth/login", params={"next": "/guide"})
    assert login.headers["location"].startswith("https://github.com/login/oauth/authorize?client_id=Iv1.abc")
    state = httpx.URL(login.headers["location"]).params["state"]

    respx.post("https://github.com/login/oauth/access_token").mock(
        return_value=httpx.Response(200, json={"access_token": "ghu_1", "refresh_token": "ghr_1", "expires_in": 28800})
    )
    respx.get("https://api.github.com/user").mock(return_value=httpx.Response(200, json={"login": "ada"}))
    done = client.get("/api/auth/callback", params={"code": "c", "state": state})
    assert done.headers["location"] == "/guide"
    assert sessions.exists(done.cookies.get("ohara_session"))


def test_sign_in_rejects_wrong_state(client, configure):
    configure(private=True)
    client.get("/api/auth/login")
    assert client.get("/api/auth/callback", params={"code": "c", "state": "forged"}).status_code == 400


def test_sign_in_never_redirects_off_site():
    from ohara.main import safe_next

    assert safe_next("//evil.com") == "/"
    assert safe_next("https://evil.com") == "/"
    assert safe_next("/guide") == "/guide"


def test_page_paths_cannot_escape_docs(client, configure, data_dir):
    configure(private=False)
    assert client.get("/api/page", params={"path": "../settings"}).status_code == 404
    assert client.get("/api/files/../settings.json").status_code == 404
