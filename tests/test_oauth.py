"""Sign in with Google. Google's token endpoint is replaced by a stand-in that returns an ID token,
so these run offline; a real sign-in needs GOOGLE_CLIENT_ID/SECRET in .env."""
import base64
import json
import time
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from app import accounts, db, oauth

CLIENT = "client-123.apps.googleusercontent.com"


@pytest.fixture(autouse=True)
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_MODE", "demo")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("GOOGLE_CLIENT_ID", CLIENT)
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "secret")
    monkeypatch.setenv("APP_BASE_URL", "http://127.0.0.1:8000")
    monkeypatch.setenv("FRONTEND_BASE_URL", "http://localhost:8080")
    monkeypatch.delenv("GOOGLE_REDIRECT_URI", raising=False)


@pytest.fixture
def conn(tmp_path):
    c = db.connect(str(tmp_path / "test.db"))
    db.init_db(c)
    return c


def id_token(**claims):
    body = {"iss": "https://accounts.google.com", "aud": CLIENT, "exp": int(time.time()) + 300,
            "sub": "google-1", "email": "Student@Example.com", "email_verified": True, **claims}
    enc = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()
    return f"{enc({'alg': 'RS256'})}.{enc(body)}.sig"


def google(**claims):
    """Stand-in for the token exchange. Echoes the nonce from the consent URL unless overridden."""
    def exchange(code, verifier):
        assert code == "auth-code" and verifier
        return {"id_token": id_token(**{"nonce": google.nonce, **claims})}
    return exchange


def begin(conn, next_path="/explore"):
    url, state = oauth.start(conn, next_path)
    q = parse_qs(urlparse(url).query)
    assert q["redirect_uri"] == ["http://127.0.0.1:8000/api/auth/google/callback"]
    assert q["code_challenge_method"] == ["S256"] and q["client_id"] == [CLIENT]
    google.nonce = q["nonce"][0]
    return state


def test_new_google_user_gets_an_account_and_session(conn):
    state = begin(conn)
    code, next_path = oauth.finish(conn, state, "auth-code", state, exchange=google())
    assert next_path == "/explore"
    out = oauth.redeem(conn, code)
    assert out["created"] is True and out["user"]["email"] == "student@example.com"
    assert accounts.user_for_token(conn, out["token"])["user_id"] == out["user"]["user_id"]
    with pytest.raises(accounts.AuthError, match="Google"):
        accounts.login(conn, "student@example.com", "password123")
    # The login code works once.
    with pytest.raises(accounts.AuthError):
        oauth.redeem(conn, code)


def test_returning_user_matches_by_google_id_even_if_email_changed(conn):
    state = begin(conn)
    first = oauth.redeem(conn, oauth.finish(conn, state, "auth-code", state, exchange=google())[0])
    state = begin(conn)
    again = oauth.redeem(conn, oauth.finish(conn, state, "auth-code", state,
                                            exchange=google(email="new@example.com"))[0])
    assert again["user"]["user_id"] == first["user"]["user_id"] and again["created"] is False


def test_existing_password_account_is_taken_over_by_verified_owner(conn):
    squatter = accounts.signup(conn, "student@example.com", "password123")
    state = begin(conn)
    out = oauth.redeem(conn, oauth.finish(conn, state, "auth-code", state, exchange=google())[0])
    assert out["user"]["user_id"] == squatter["user"]["user_id"] and out["created"] is False
    # Whoever registered the address without proving it is signed out and can't log in again.
    with pytest.raises(accounts.AuthError):
        accounts.user_for_token(conn, squatter["token"])
    with pytest.raises(accounts.AuthError):
        accounts.login(conn, "student@example.com", "password123")


@pytest.mark.parametrize("claims, message", [
    ({"aud": "someone-else"}, "different app"),
    ({"iss": "https://evil.example"}, "didn't come from Google"),
    ({"exp": int(time.time()) - 3600}, "expired"),
    ({"nonce": "wrong"}, "doesn't match"),
    ({"email_verified": False}, "verified email"),
])
def test_bad_id_tokens_are_rejected(conn, claims, message):
    state = begin(conn)
    with pytest.raises(oauth.OAuthError, match=message):
        oauth.finish(conn, state, "auth-code", state, exchange=google(**claims))
    assert conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0


def test_state_must_match_cookie_and_is_single_use(conn):
    state = begin(conn)
    with pytest.raises(oauth.OAuthError, match="another browser"):
        oauth.finish(conn, state, "auth-code", "other", exchange=google())
    oauth.finish(conn, state, "auth-code", state, exchange=google())
    with pytest.raises(oauth.OAuthError, match="expired"):
        oauth.finish(conn, state, "auth-code", state, exchange=google())


@pytest.mark.parametrize("raw, safe", [("/map?day=2026-11-12", "/map?day=2026-11-12"), ("//evil.com", "/"),
                                       ("https://evil.com", "/"), ("/\\evil.com", "/"), (None, "/")])
def test_next_path_stays_on_site(raw, safe):
    assert oauth.safe_next(raw) == safe


def test_http_flow_end_to_end(monkeypatch):
    from app.main import app
    monkeypatch.setattr(oauth, "exchange_code", lambda code, verifier: google()(code, verifier))
    with TestClient(app, base_url="http://127.0.0.1:8000") as api:
        assert api.get("/api/auth/providers").json() == {"google": True}
        start = api.get("/api/auth/google/start", params={"next": "/map"}, follow_redirects=False)
        assert start.status_code == 303 and start.headers["location"].startswith(oauth.AUTH_URL)
        q = parse_qs(urlparse(start.headers["location"]).query)
        google.nonce = q["nonce"][0]
        back = api.get("/api/auth/google/callback", params={"state": q["state"][0], "code": "auth-code"},
                       follow_redirects=False)
        target = urlparse(back.headers["location"])
        assert target.netloc == "localhost:8080" and target.path == "/auth/callback"
        frag = parse_qs(target.fragment)
        assert frag["next"] == ["/map"] and "token" not in frag
        session = api.post("/api/auth/google/redeem", json={"code": frag["code"][0]}).json()
        me = api.get("/api/me", headers={"Authorization": f"Bearer {session['token']}"}).json()
        assert me["email"] == "student@example.com"
        # Without the browser cookie from /start, a callback is refused.
        api.cookies.clear()
        start = api.get("/api/auth/google/start", follow_redirects=False)
        q = parse_qs(urlparse(start.headers["location"]).query)
        api.cookies.clear()
        back = api.get("/api/auth/google/callback", params={"state": q["state"][0], "code": "auth-code"},
                       follow_redirects=False)
        assert "error" in parse_qs(urlparse(back.headers["location"]).fragment)


def test_disabled_without_credentials(monkeypatch, conn):
    monkeypatch.delenv("GOOGLE_CLIENT_SECRET")
    assert oauth.enabled() is False
    with pytest.raises(oauth.OAuthError, match="isn't set up"):
        oauth.start(conn, "/")
