"""Sign in with Google: OpenID Connect authorization code flow with PKCE, run entirely by the backend.

1. `start` stores a random state, PKCE verifier and nonce, and returns Google's consent URL. The same
   state also goes into an HttpOnly cookie, so a callback only completes in the browser that began it.
2. `finish` checks state and cookie, trades the code for an ID token with the client secret, validates
   the token's claims, and finds or creates the Quad user.
3. The browser is sent back to the website with a one-time login code in the URL fragment (never a
   session token). The website trades it for a normal session with `redeem`.

The ID token comes straight from Google's token endpoint over TLS, authenticated with our client
secret, so its claims are validated but its signature is not (OpenID Connect Core 3.1.3.7).
"""
from __future__ import annotations

import base64
import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx

from . import accounts, config

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
ISSUERS = {"https://accounts.google.com", "accounts.google.com"}
STATE_MINUTES = 10
CODE_SECONDS = 120
COOKIE = "quad_oauth_state"


class OAuthError(Exception):
    """The sign-in can't complete. The message is safe to show the user."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def enabled() -> bool:
    return bool(config.get("GOOGLE_CLIENT_ID") and config.get("GOOGLE_CLIENT_SECRET"))


def redirect_uri() -> str:
    base = config.get("APP_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    return config.get("GOOGLE_REDIRECT_URI") or f"{base}/api/auth/google/callback"


def frontend_url(path: str) -> str:
    return config.get("FRONTEND_BASE_URL", "http://localhost:8080").rstrip("/") + path


def safe_next(path: str | None) -> str:
    """Only same-site paths, so the sign-in can't be used to bounce users to another site."""
    if not path or not path.startswith("/") or path.startswith("//") or "\\" in path:
        return "/"
    return path[:300]


def _prune(conn) -> None:
    now = _iso(_now())
    conn.execute("DELETE FROM oauth_states WHERE expires_at <= ?", (now,))
    conn.execute("DELETE FROM login_codes WHERE expires_at <= ?", (now,))


# ---------------------------------------------------------------- 1. start

def start(conn, next_path: str | None) -> tuple[str, str]:
    """Returns (Google consent URL, state for the browser cookie)."""
    if not enabled():
        raise OAuthError("Google sign-in isn't set up on this server.")
    state, verifier, nonce = (secrets.token_urlsafe(32) for _ in range(3))
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    with conn:
        _prune(conn)
        conn.execute("INSERT INTO oauth_states (state_hash, verifier, nonce, next_path, expires_at) "
                     "VALUES (?,?,?,?,?)", (_sha(state), verifier, nonce, safe_next(next_path),
                                            _iso(_now() + timedelta(minutes=STATE_MINUTES))))
    query = urlencode({
        "client_id": config.get("GOOGLE_CLIENT_ID"), "redirect_uri": redirect_uri(), "response_type": "code",
        "scope": "openid email profile", "state": state, "nonce": nonce, "code_challenge": challenge,
        "code_challenge_method": "S256", "prompt": "select_account",
    })
    return f"{AUTH_URL}?{query}", state


# ---------------------------------------------------------------- 2. callback

def exchange_code(code: str, verifier: str) -> dict:
    """Trade the authorization code for tokens at Google. Replaced in tests."""
    try:
        resp = httpx.post(TOKEN_URL, timeout=15, data={
            "code": code, "client_id": config.get("GOOGLE_CLIENT_ID"),
            "client_secret": config.get("GOOGLE_CLIENT_SECRET"), "redirect_uri": redirect_uri(),
            "grant_type": "authorization_code", "code_verifier": verifier})
    except httpx.HTTPError as exc:
        raise OAuthError("Couldn't reach Google. Try again.") from exc
    if resp.status_code != 200:
        raise OAuthError("Google didn't accept the sign-in. Try again.")
    return resp.json()


def _claims(id_token: str) -> dict:
    try:
        payload = id_token.split(".")[1]
        return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except (IndexError, ValueError) as exc:
        raise OAuthError("Google sent an unreadable sign-in.") from exc


def _check(claims: dict, nonce: str) -> None:
    if claims.get("iss") not in ISSUERS:
        raise OAuthError("That sign-in didn't come from Google.")
    aud = claims.get("aud")
    if config.get("GOOGLE_CLIENT_ID") not in (aud if isinstance(aud, list) else [aud]):
        raise OAuthError("That sign-in was meant for a different app.")
    if not isinstance(claims.get("exp"), (int, float)) or claims["exp"] < _now().timestamp() - 60:
        raise OAuthError("That sign-in expired. Try again.")
    if not claims.get("nonce") or not secrets.compare_digest(str(claims["nonce"]), nonce):
        raise OAuthError("That sign-in doesn't match this request. Try again.")
    if not claims.get("sub"):
        raise OAuthError("Google didn't say which account signed in.")
    if not claims.get("email") or claims.get("email_verified") is not True:
        raise OAuthError("Your Google account needs a verified email address.")


def _user_for(conn, claims: dict) -> tuple[str, bool]:
    """(user_id, created). Must run inside the caller's transaction."""
    sub, email = str(claims["sub"]), accounts.normalize_email(claims["email"])
    row = conn.execute("SELECT user_id FROM user_identities WHERE provider='google' AND subject=?",
                       (sub,)).fetchone()
    if row:
        return row["user_id"], False
    row = conn.execute("SELECT user_id FROM users WHERE email=?", (email,)).fetchone()
    if row:
        # Quad never verified the email of a password sign-up, so anyone could have registered this
        # address first. Google has verified it: hand the account to this person, and sign out and
        # disable the old password so whoever registered it can't keep a way in.
        uid, created = row["user_id"], False
        conn.execute("UPDATE users SET password_hash='google' WHERE user_id=?", (uid,))
        conn.execute("DELETE FROM sessions WHERE user_id=?", (uid,))
    else:
        uid, created = f"usr-{secrets.token_hex(5)}", True
        # 'google' is not a valid scrypt hash, so password login is impossible for this account.
        conn.execute("INSERT INTO users (user_id, email, password_hash, created_at) VALUES (?,?,?,?)",
                     (uid, email, "google", _iso(_now())))
    conn.execute("INSERT INTO user_identities (provider, subject, user_id, email, created_at) "
                 "VALUES ('google',?,?,?,?)", (sub, uid, email, _iso(_now())))
    return uid, created


def finish(conn, state: str | None, code: str | None, cookie_state: str | None,
           exchange=None) -> tuple[str, str]:
    """Complete the callback. Returns (one-time login code, next path)."""
    if not state or not code:
        raise OAuthError("The sign-in was cancelled or incomplete.")
    if not cookie_state or not secrets.compare_digest(state, cookie_state):
        raise OAuthError("This sign-in started in another browser or tab. Try again here.")
    with conn:
        _prune(conn)
        row = conn.execute("DELETE FROM oauth_states WHERE state_hash=? RETURNING verifier, nonce, next_path",
                           (_sha(state),)).fetchone()
    if not row:
        raise OAuthError("That sign-in link expired. Try again.")
    # The network call happens with no transaction open.
    tokens = (exchange or exchange_code)(code, row["verifier"])
    claims = _claims(tokens.get("id_token") or "")
    _check(claims, row["nonce"])
    login_code = secrets.token_urlsafe(32)
    with conn:
        conn.execute("BEGIN IMMEDIATE")
        uid, created = _user_for(conn, claims)
        conn.execute("INSERT INTO login_codes (code_hash, user_id, created, expires_at) VALUES (?,?,?,?)",
                     (_sha(login_code), uid, int(created),
                      _iso(_now() + timedelta(seconds=CODE_SECONDS))))
    return login_code, row["next_path"]


# ---------------------------------------------------------------- 3. website

def redeem(conn, login_code: str) -> dict:
    """Trade a one-time login code for a session, like a password login returns."""
    with conn:
        row = conn.execute("DELETE FROM login_codes WHERE code_hash=? AND expires_at > ? "
                           "RETURNING user_id, created", (_sha(login_code), _iso(_now()))).fetchone()
        if not row:
            raise accounts.AuthError("that sign-in link expired, please try again")
        token = accounts._new_session(conn, row["user_id"])
    return {"token": token, "user": accounts.get_user(conn, row["user_id"]), "created": bool(row["created"])}
