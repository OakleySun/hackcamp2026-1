"""Student accounts: email + password sign-up, bearer-token sessions, and the setup profile.

Passwords are hashed with scrypt (stdlib). Session tokens are random, returned once, and stored
only as a SHA-256 hash, the same pattern subscriptions use for verify/manage tokens.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
from datetime import date, datetime, timedelta, timezone

from .extract import TOPICS
from .models import ProfileRequest

SESSION_DAYS = 30
MIN_AGE = 13
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_SCRYPT = {"n": 2**14, "r": 8, "p": 1, "dklen": 32}


class AuthError(Exception):
    """Wrong credentials or a missing/expired session (HTTP 401)."""


class EmailTaken(Exception):
    """Sign-up with an email that already has an account (HTTP 409)."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def _sha(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    return f"scrypt${salt.hex()}${digest.hex()}"


def check_password(password: str, stored: str) -> bool:
    try:
        scheme, salt, digest = stored.split("$")
    except ValueError:
        return False
    if scheme != "scrypt":
        return False
    got = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), **_SCRYPT)
    return hmac.compare_digest(got.hex(), digest)


def normalize_email(email: str) -> str:
    email = email.strip().lower()
    if not EMAIL_RE.match(email):
        raise ValueError("enter a valid email address")
    return email


# ---------------------------------------------------------------- sessions

def _new_session(conn, user_id: str) -> str:
    token = secrets.token_urlsafe(32)
    now = _now()
    conn.execute("INSERT INTO sessions (token_hash, user_id, created_at, expires_at) VALUES (?,?,?,?)",
                 (_sha(token), user_id, _iso(now), _iso(now + timedelta(days=SESSION_DAYS))))
    return token


def signup(conn, email: str, password: str) -> dict:
    email = normalize_email(email)
    uid = f"usr-{secrets.token_hex(5)}"
    with conn:
        if conn.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
            raise EmailTaken(email)
        conn.execute("INSERT INTO users (user_id, email, password_hash, created_at) VALUES (?,?,?,?)",
                     (uid, email, hash_password(password), _iso(_now())))
        token = _new_session(conn, uid)
    return {"token": token, "user": get_user(conn, uid)}


def login(conn, email: str, password: str) -> dict:
    row = conn.execute("SELECT user_id, password_hash FROM users WHERE email=?",
                       (email.strip().lower(),)).fetchone()
    # Hash anyway when the email is unknown so response time doesn't reveal which emails exist.
    ok = check_password(password, row["password_hash"] if row else hash_password("x" * 8))
    if not row or not ok:
        raise AuthError("wrong email or password")
    with conn:
        token = _new_session(conn, row["user_id"])
    return {"token": token, "user": get_user(conn, row["user_id"])}


def user_for_token(conn, token: str) -> dict:
    if not token:
        raise AuthError("not signed in")
    row = conn.execute("SELECT user_id, expires_at FROM sessions WHERE token_hash=?", (_sha(token),)).fetchone()
    if not row or row["expires_at"] <= _iso(_now()):
        raise AuthError("session expired, please sign in again")
    return get_user(conn, row["user_id"])


def logout(conn, token: str) -> None:
    with conn:
        conn.execute("DELETE FROM sessions WHERE token_hash=?", (_sha(token),))


# ---------------------------------------------------------------- profile

def get_user(conn, user_id: str) -> dict:
    row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
    out = {k: row[k] for k in ("user_id", "email", "created_at", "onboarded_at", "birthday", "major",
                                "gender", "gender_detail")}
    out["interests"] = json.loads(row["interests"])
    out["hobbies"] = json.loads(row["hobbies"])
    out["onboarded"] = row["onboarded_at"] is not None
    return out


def _age(birthday: date, today: date) -> int:
    return today.year - birthday.year - ((today.month, today.day) < (birthday.month, birthday.day))


def save_profile(conn, user_id: str, p: ProfileRequest) -> dict:
    """Validate and store setup answers. Marks the account as onboarded."""
    if p.birthday is not None:
        age = _age(p.birthday, date.today())
        if p.birthday > date.today() or age > 120:
            raise ValueError("enter a real birthday")
        if age < MIN_AGE:
            raise ValueError(f"you must be at least {MIN_AGE} to make an account")
    interests = list(dict.fromkeys(t for t in p.interests if t in TOPICS))
    if not interests:
        raise ValueError("pick at least one interest")
    hobbies = []
    for h in p.hobbies:
        h = re.sub(r"\s+", " ", h).strip()[:40]
        if h and h.lower() not in {x.lower() for x in hobbies}:
            hobbies.append(h)
    major = (p.major or "").strip() or None
    detail = (p.gender_detail or "").strip() or None if p.gender == "self-describe" else None
    with conn:
        conn.execute(
            "UPDATE users SET birthday=?, major=?, gender=?, gender_detail=?, interests=?, hobbies=?, "
            "onboarded_at=COALESCE(onboarded_at, ?) WHERE user_id=?",
            (p.birthday.isoformat() if p.birthday else None, major, p.gender, detail,
             json.dumps(interests), json.dumps(hobbies), _iso(_now()), user_id))
    return get_user(conn, user_id)
