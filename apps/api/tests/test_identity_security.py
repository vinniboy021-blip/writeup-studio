from datetime import timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.config import Settings, settings
from app.db import utcnow
from app.models import SessionModel, Team, TeamMember, User, Writeup
from app.schemas import Document
from app.security import authorize, password_hash, verify_password, visible_query


def test_register_argon_cookie_and_safe_me(client, auth, db):
    user = db.get(User, auth["user"]["id"])
    assert user.password_hash.startswith("$argon2id$")
    assert verify_password(auth["password"], user.password_hash)
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 200
    assert response.json()["user"] == auth["user"]
    assert "password" not in response.text
    assert response.json()["csrf_token"] == auth["csrf_token"]
    sessions = client.get("/api/v1/auth/sessions").json()
    assert sessions["total"] == 1
    assert "token_hash" not in str(sessions)
    assert sessions["items"][0]["current"]


def test_login_cookie_logout_csrf_and_revocation(client, auth):
    assert client.post("/api/v1/auth/logout").status_code == 403
    logout = client.post("/api/v1/auth/logout", headers=auth["headers"])
    assert logout.status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401
    response = client.post("/api/v1/auth/login", json={"email": auth["user"]["email"], "password": auth["password"]})
    assert response.status_code == 200
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie
    assert "password_hash" not in response.text
    assert client.get("/api/v1/auth/me").status_code == 200


def test_account_registration_cannot_elevate(client):
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "admin@example.org", "name": "Admin", "password": "Password-secure-123", "is_admin": True},
    )
    assert response.status_code == 422
    assert "Password-secure-123" not in response.text
    assert response.json()["error"]["code"] == "validation_error"


def test_csrf_origin_and_password_rotates_other_sessions(client, auth):
    old_cookie = auth["cookies"]["ctf_session"]
    second = client.post(
        "/api/v1/auth/login", json={"email": auth["user"]["email"], "password": auth["password"]}
    ).json()
    invalid_origin = client.post(
        "/api/v1/auth/password",
        headers={"X-CSRF-Token": second["csrf_token"], "Origin": "https://evil.example.org"},
        json={"current_password": auth["password"], "new_password": "New-safe-password-456"},
    )
    assert invalid_origin.status_code == 403
    response = client.post(
        "/api/v1/auth/password",
        headers={"X-CSRF-Token": second["csrf_token"]},
        json={"current_password": auth["password"], "new_password": "New-safe-password-456"},
    )
    assert response.status_code == 200
    assert response.json()["csrf_token"] != second["csrf_token"]
    client.cookies.set("ctf_session", old_cookie)
    assert client.get("/api/v1/auth/me").status_code == 401
    assert (
        client.post(
            "/api/v1/auth/login", json={"email": auth["user"]["email"], "password": auth["password"]}
        ).status_code
        == 401
    )


def test_session_expiration(client, auth, db):
    session = db.scalar(select(SessionModel).where(SessionModel.user_id == auth["user"]["id"]))
    session.expires_at = utcnow() - timedelta(seconds=1)
    db.commit()
    assert client.get("/api/v1/auth/me").status_code == 401


def test_login_bruteforce_rate_limit(client, auth):
    results = [
        client.post("/api/v1/auth/login", json={"email": auth["user"]["email"], "password": "wrong"}).status_code
        for _ in range(settings.login_rate_limit + 1)
    ]
    assert 401 in results and results[-1] == 429


def test_owner_private_and_team_roles(db):
    owner = User(email="owner@test.org", name="Owner", password_hash=password_hash.hash("Password-123456"))
    outsider = User(email="other@test.org", name="Other", password_hash=password_hash.hash("Password-123456"))
    db.add_all([owner, outsider])
    db.flush()
    team = Team(name="Team", owner_id=owner.id)
    db.add(team)
    db.flush()
    db.add(TeamMember(team_id=team.id, user_id=owner.id, role="manager"))
    membership = TeamMember(team_id=team.id, user_id=outsider.id, role="viewer")
    db.add(membership)
    db.flush()
    private = Writeup(owner_id=owner.id, title="Private", document={"schema_version": 1, "sections": []})
    shared = Writeup(
        owner_id=owner.id,
        team_id=team.id,
        visibility="team",
        title="Shared",
        document={"schema_version": 1, "sections": []},
    )
    db.add_all([private, shared])
    db.flush()
    assert authorize(db, owner, private) is private
    with pytest.raises(HTTPException) as denied:
        authorize(db, outsider, private)
    assert denied.value.status_code == 404
    assert authorize(db, outsider, shared) is shared
    with pytest.raises(HTTPException):
        authorize(db, outsider, shared, "write")
    membership.role = "reviewer"
    db.flush()
    assert authorize(db, outsider, shared, "comment") is shared
    assert authorize(db, outsider, shared, "review") is shared
    with pytest.raises(HTTPException):
        authorize(db, outsider, shared, "write")
    assert [row.id for row in db.scalars(visible_query(select(Writeup), Writeup, outsider, db))] == [shared.id]
    db.delete(membership)
    db.flush()
    with pytest.raises(HTTPException):
        authorize(db, outsider, shared)


def test_strict_document_uniqueness_schema_and_limits(monkeypatch):
    Document.model_validate(
        {"schema_version": 1, "sections": [{"id": "s1", "title": "Title", "markdown": "actual note"}]}
    )
    with pytest.raises(ValueError):
        Document.model_validate({"schema_version": 2, "sections": []})
    with pytest.raises(ValueError):
        Document.model_validate(
            {"schema_version": 1, "sections": [{"id": "s1", "title": "A"}, {"id": "s1", "title": "B"}]}
        )
    monkeypatch.setattr(settings, "max_document_bytes", 100)
    with pytest.raises(ValueError):
        Document.model_validate({"schema_version": 1, "sections": [{"id": "s1", "title": "A", "markdown": "a" * 100}]})


def test_production_configuration_fails_closed():
    with pytest.raises(ValueError):
        Settings(environment="production", database_url="sqlite://", cookie_secure=False, _env_file=None)
    valid = Settings(
        environment="production",
        database_url="postgresql+psycopg://u:p@db/studio",
        cookie_secure=True,
        secret_key="a" * 48,
        cors_origins="https://ctf.example.org",
        rate_limit_backend="redis",
        queue_enabled=True,
        _env_file=None,
    )
    assert valid.cookie_secure
    with pytest.raises(ValueError):
        Settings(cors_origins="*", _env_file=None)
