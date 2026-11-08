"""Account sign-up, login, sessions and the setup profile, through the HTTP API."""
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app import accounts
from app.main import app

PROFILE = {
    "birthday": "2005-03-14",
    "major": "Computer Science",
    "gender": "prefer-not",
    "interests": ["tech", "arts", "not-a-topic"],
    "hobbies": ["Climbing", "climbing", "  film   photography "],
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "accounts.db"))
    with TestClient(app) as c:
        yield c


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def signup(client, email="student@example.test", password="correct horse"):
    r = client.post("/api/auth/signup", json={"email": email, "password": password})
    assert r.status_code == 201, r.text
    return r.json()


def test_signup_returns_session_and_unonboarded_user(client):
    out = signup(client, email="  Student@Example.TEST ")
    assert out["user"]["email"] == "student@example.test"
    assert out["user"]["onboarded"] is False
    assert client.get("/api/me", headers=auth(out["token"])).json()["user_id"] == out["user"]["user_id"]


def test_duplicate_email_and_bad_input(client):
    signup(client)
    assert client.post("/api/auth/signup", json={"email": "student@example.test", "password": "another one"}).status_code == 409
    assert client.post("/api/auth/signup", json={"email": "nope", "password": "long enough"}).status_code == 422
    assert client.post("/api/auth/signup", json={"email": "a@b.co", "password": "short"}).status_code == 422


def test_login_logout(client):
    signup(client)
    assert client.post("/api/auth/login", json={"email": "student@example.test", "password": "wrong pass"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "nobody@example.test", "password": "whatever1"}).status_code == 401
    token = client.post("/api/auth/login", json={"email": "student@example.test", "password": "correct horse"}).json()["token"]
    assert client.get("/api/me", headers=auth(token)).status_code == 200
    assert client.post("/api/auth/logout", headers=auth(token)).status_code == 204
    assert client.get("/api/me", headers=auth(token)).status_code == 401


def test_me_requires_a_session(client):
    assert client.get("/api/me").status_code == 401
    assert client.get("/api/me", headers=auth("made-up")).status_code == 401


def test_profile_setup_cleans_answers_and_onboards(client):
    token = signup(client)["token"]
    r = client.put("/api/me/profile", headers=auth(token), json=PROFILE)
    assert r.status_code == 200, r.text
    user = r.json()
    assert user["onboarded"] is True
    assert user["interests"] == ["tech", "arts"]
    assert user["hobbies"] == ["Climbing", "film photography"]
    assert user["birthday"] == "2005-03-14"
    assert client.get("/api/me", headers=auth(token)).json()["major"] == "Computer Science"


def test_profile_validation(client):
    token = signup(client)["token"]
    put = lambda **over: client.put("/api/me/profile", headers=auth(token), json={**PROFILE, **over})
    assert put(interests=[]).status_code == 422
    assert put(birthday=date.today().replace(year=date.today().year + 1).isoformat()).status_code == 422
    assert put(birthday=f"{date.today().year - 10}-01-01").status_code == 422  # under 13
    assert put(gender="robot").status_code == 422
    # optional answers may be skipped
    assert put(birthday=None, major=None, gender=None, hobbies=[]).status_code == 200


def test_self_described_gender_keeps_detail_only_when_chosen(client):
    token = signup(client)["token"]
    put = lambda **over: client.put("/api/me/profile", headers=auth(token), json={**PROFILE, **over}).json()
    assert put(gender="self-describe", gender_detail="genderfluid")["gender_detail"] == "genderfluid"
    assert put(gender="woman", gender_detail="ignored")["gender_detail"] is None


def test_passwords_are_hashed():
    h = accounts.hash_password("correct horse")
    assert "correct horse" not in h
    assert accounts.check_password("correct horse", h)
    assert not accounts.check_password("wrong", h)
