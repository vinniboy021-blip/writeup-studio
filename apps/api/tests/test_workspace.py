# SPDX-License-Identifier: MIT
"""Authorization, atomic updates and collaboration tests against an isolated DB."""

from datetime import timedelta
import hashlib

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models as m
from app.modules.workspace import schemas as s
from app.modules.workspace import services as service


@pytest.fixture
def workspace(engine):
    with Session(engine, expire_on_commit=False) as db:
        users = {}
        for role in ["owner", "manager", "editor", "reviewer", "viewer", "outsider", "admin"]:
            user = m.User(
                email=f"{role}@example.test",
                name=role,
                password_hash="test-only-argon-placeholder",
                is_admin=role == "admin",
                is_active=True,
            )
            db.add(user)
            db.flush()
            users[role] = user
        team = m.Team(owner_id=users["owner"].id, name="Equipe")
        db.add(team)
        db.flush()
        for role in ["owner", "manager", "editor", "reviewer", "viewer"]:
            db.add(m.TeamMember(team_id=team.id, user_id=users[role].id, role="manager" if role == "owner" else role))
        db.commit()
        service.seed_workspace(db)
        yield db, users, team


def expect_http(code, callable_):
    with pytest.raises(HTTPException) as error:
        callable_()
    assert error.value.status_code == code


def team_competition(db, owner, team):
    return service.create_competition(
        db, owner, s.CompetitionCreate(name="Competição real", team_id=team.id, visibility="team", tags=["ctf"])
    )


def team_writeup(db, owner, team):
    item = m.Writeup(
        owner_id=owner.id,
        team_id=team.id,
        visibility="team",
        title="Documento",
        document={
            "schema_version": 1,
            "sections": [{"id": "objective", "title": "Objetivo", "markdown": "Análise autorizada"}],
        },
        version=1,
    )
    db.add(item)
    db.flush()
    db.add(
        m.WriteupRevision(writeup_id=item.id, version=1, title=item.title, document=item.document, author_id=owner.id)
    )
    db.commit()
    return item


def test_private_team_isolation_and_roles(workspace):
    db, users, team = workspace
    private = service.create_competition(db, users["owner"], s.CompetitionCreate(name="Privado", team_id=team.id))
    shared = team_competition(db, users["owner"], team)
    for role in ["editor", "reviewer", "viewer"]:
        expect_http(404, lambda: service.resource(db, users[role], m.Competition, private["id"]))
        result = service.list_resources(db, users[role], m.Competition, 1, 25)
        assert [item["id"] for item in result["items"]] == [shared["id"]]
    expect_http(403, lambda: service.resource(db, users["outsider"], m.Competition, shared["id"]))
    for role in ["viewer", "reviewer"]:
        expect_http(
            403,
            lambda: service.patch_competition(
                db, users[role], shared["id"], s.CompetitionPatch(expected_version=1, name="Alterado")
            ),
        )
    patched = service.patch_competition(
        db, users["editor"], shared["id"], s.CompetitionPatch(expected_version=1, name="Editado")
    )
    assert patched["name"] == "Editado" and patched["version"] == 2


def test_cas_resource_update_and_delete(workspace):
    db, users, team = workspace
    item = team_competition(db, users["owner"], team)
    service.patch_competition(db, users["owner"], item["id"], s.CompetitionPatch(expected_version=1, name="V2"))
    expect_http(
        409,
        lambda: service.patch_competition(
            db, users["editor"], item["id"], s.CompetitionPatch(expected_version=1, name="Perda silenciosa")
        ),
    )
    assert db.get(m.Competition, item["id"]).name == "V2"
    expect_http(409, lambda: service.soft_delete(db, users["owner"], m.Competition, item["id"], 1))
    service.soft_delete(db, users["owner"], m.Competition, item["id"], 2)
    expect_http(404, lambda: service.resource(db, users["owner"], m.Competition, item["id"]))


def test_foreign_relationship_and_assignments(workspace):
    db, users, team = workspace
    parent = team_competition(db, users["owner"], team)
    expect_http(
        422,
        lambda: service.create_challenge(
            db, users["owner"], s.ChallengeCreate(name="Cross-space", competition_id=parent["id"])
        ),
    )
    expect_http(
        422,
        lambda: service.create_challenge(
            db,
            users["owner"],
            s.ChallengeCreate(
                name="Outsider assigned",
                competition_id=parent["id"],
                team_id=team.id,
                visibility="team",
                assignee_ids=[users["outsider"].id],
            ),
        ),
    )
    db.rollback()
    item = service.create_challenge(
        db,
        users["owner"],
        s.ChallengeCreate(
            name="Web challenge",
            category="Web",
            competition_id=parent["id"],
            team_id=team.id,
            visibility="team",
            assignee_ids=[users["editor"].id],
        ),
    )
    assert item["assignee_ids"] == [users["editor"].id]
    result = service.patch_challenge(
        db,
        users["editor"],
        item["id"],
        s.ChallengePatch(expected_version=1, status="solved", assignee_ids=[users["reviewer"].id]),
    )
    assert result["status"] == "solved" and result["assignee_ids"] == [users["reviewer"].id]
    expect_http(
        409,
        lambda: service.patch_competition(
            db, users["owner"], parent["id"], s.CompetitionPatch(expected_version=1, team_id=None, visibility="private")
        ),
    )


def test_custom_category_scoping(workspace):
    db, users, team = workspace
    custom = m.Category(owner_id=users["owner"].id, name="Custom")
    db.add(custom)
    db.commit()
    service.validate_category(db, users["owner"], "Custom", None)
    expect_http(422, lambda: service.validate_category(db, users["outsider"], "Custom", None))
    expect_http(422, lambda: service.validate_category(db, users["owner"], "Missing", team.id))


def test_member_response_and_last_manager_guard(workspace):
    db, users, team = workspace
    result = service.team_members(db, users["viewer"], team.id)
    assert all("password_hash" not in entry["user"] for entry in result["items"])
    expect_http(403, lambda: service.set_member(db, users["editor"], team.id, users["viewer"].id, "manager"))
    service.set_member(db, users["owner"], team.id, users["manager"].id, "viewer")
    expect_http(409, lambda: service.set_member(db, users["owner"], team.id, users["owner"].id, "viewer"))
    expect_http(409, lambda: service.remove_member(db, users["owner"], team.id, users["owner"].id))


def test_invites_email_expiry_single_use_no_role_escalation(workspace):
    db, users, team = workspace
    invite = service.create_invite(
        db, users["owner"], team.id, s.InviteInput(email=users["outsider"].email, role="editor")
    )
    stored = db.get(m.TeamInvite, invite["id"])
    assert stored.token_hash == hashlib.sha256(invite["token"].encode()).hexdigest()
    assert stored.token_hash != invite["token"]
    expect_http(403, lambda: service.accept_invite(db, users["viewer"], invite["token"]))
    accepted = service.accept_invite(db, users["outsider"], invite["token"])
    assert accepted["role"] == "editor"
    expect_http(410, lambda: service.accept_invite(db, users["outsider"], invite["token"]))
    expired = service.create_invite(
        db, users["owner"], team.id, s.InviteInput(email=users["viewer"].email, role="manager")
    )
    db.get(m.TeamInvite, expired["id"]).expires_at = service.now() - timedelta(seconds=1)
    db.commit()
    expect_http(410, lambda: service.accept_invite(db, users["viewer"], expired["token"]))
    older = service.create_invite(
        db, users["owner"], team.id, s.InviteInput(email=users["viewer"].email, role="manager")
    )
    assert service.accept_invite(db, users["viewer"], older["token"])["role"] == "viewer"


def test_templates_real_defaults_version_import_and_acl(workspace):
    db, users, team = workspace
    defaults = db.scalars(service.templates_query(db, users["outsider"])).all()
    assert len(defaults) == 10
    assert all(not section["markdown"] for template in defaults for section in template.document["sections"])
    expect_http(
        403,
        lambda: service.patch_template(
            db, users["owner"], defaults[0].id, s.TemplatePatch(expected_version=1, name="Forbidden")
        ),
    )
    created = service.create_template(
        db, users["owner"], s.TemplateImport(name="Personalizado", document=defaults[0].document)
    )
    updated = service.patch_template(db, users["owner"], created["id"], s.TemplatePatch(expected_version=1, name="V2"))
    assert updated["version"] == 2
    revisions = db.scalars(
        select(m.TemplateRevision)
        .where(m.TemplateRevision.template_id == created["id"])
        .order_by(m.TemplateRevision.version)
    ).all()
    assert [revision.name for revision in revisions] == ["Personalizado", "V2"]
    expect_http(
        409,
        lambda: service.patch_template(
            db, users["owner"], created["id"], s.TemplatePatch(expected_version=1, name="Stale")
        ),
    )
    expect_http(404, lambda: service.template_resource(db, users["outsider"], created["id"]))


def test_comments_section_validation_resolution_and_notification(workspace):
    db, users, team = workspace
    item = team_writeup(db, users["owner"], team)
    expect_http(
        422,
        lambda: service.create_comment(
            db, users["reviewer"], item.id, s.CommentCreate(body="Texto", section_id="missing")
        ),
    )
    created = service.create_comment(
        db, users["reviewer"], item.id, s.CommentCreate(body="Revisar observação", section_id="objective")
    )
    expect_http(403, lambda: service.resolve_comment(db, users["viewer"], created["id"], True))
    resolved = service.resolve_comment(db, users["reviewer"], created["id"], True)
    assert resolved["resolved_at"] is not None
    assert db.scalar(select(m.Notification).where(m.Notification.user_id == users["owner"].id)).entity_id == item.id


def test_review_cannot_self_approve_and_stale_is_rejected(workspace):
    db, users, team = workspace
    item = team_writeup(db, users["owner"], team)
    expect_http(
        422, lambda: service.create_review(db, users["owner"], item.id, s.ReviewCreate(reviewer_id=users["owner"].id))
    )
    expect_http(
        403, lambda: service.create_review(db, users["owner"], item.id, s.ReviewCreate(reviewer_id=users["viewer"].id))
    )
    review = service.create_review(db, users["owner"], item.id, s.ReviewCreate(reviewer_id=users["reviewer"].id))
    expect_http(
        403, lambda: service.decide_review(db, users["owner"], review["id"], s.ReviewDecision(decision="approved"))
    )
    item.version = 2
    db.commit()
    expect_http(
        409, lambda: service.decide_review(db, users["reviewer"], review["id"], s.ReviewDecision(decision="approved"))
    )
    current = service.create_review(db, users["owner"], item.id, s.ReviewCreate(reviewer_id=users["reviewer"].id))
    service.decide_review(
        db, users["reviewer"], current["id"], s.ReviewDecision(decision="approved", comment="Evidências conferidas")
    )
    db.expire_all()
    assert db.get(m.Writeup, item.id).approved_revision == 2


def test_review_latest_revision_author_cannot_approve(workspace):
    db, users, team = workspace
    item = team_writeup(db, users["owner"], team)
    revision = db.scalar(select(m.WriteupRevision).where(m.WriteupRevision.writeup_id == item.id))
    revision.author_id = users["reviewer"].id
    db.commit()
    expect_http(
        422,
        lambda: service.create_review(db, users["owner"], item.id, s.ReviewCreate(reviewer_id=users["reviewer"].id)),
    )


def test_dashboard_progress_and_search_scope_combined_filters(workspace):
    db, users, team = workspace
    parent = team_competition(db, users["owner"], team)
    shared = service.create_challenge(
        db,
        users["owner"],
        s.ChallengeCreate(
            name="Forensic example",
            category="Forensics",
            team_id=team.id,
            visibility="team",
            competition_id=parent["id"],
            status="solved",
            tags=["artifact"],
        ),
    )
    service.create_challenge(
        db, users["owner"], s.ChallengeCreate(name="Forensic private", category="Forensics", tags=["artifact"])
    )
    result = service.search(
        db, users["viewer"], q="Forensic", category="Forensics", tags="artifact", author_id=users["owner"].id
    )
    assert result["total"] == 1 and result["items"][0]["id"] == shared["id"]
    assert service.search(db, users["outsider"], q="Forensic")["total"] == 0
    dashboard = service.dashboard(db, users["viewer"])
    assert dashboard["competitions"] == 1 and dashboard["challenges"] == 1
    assert dashboard["competition_progress"][0]["percent"] == 100
    assert not any(
        row["entity_id"] != shared["id"] and row["entity_id"] != parent["id"] for row in dashboard["recent_activity"]
    )


def test_search_metadata_language_and_pagination(workspace):
    db, users, team = workspace
    item = team_writeup(db, users["owner"], team)
    item.tools = ["radare2"]
    item.languages = ["python"]
    item.tags = ["reverse"]
    db.commit()
    result = service.search(db, users["viewer"], tool="radare2", language="python", tags="reverse", page_size=1)
    assert result["total"] == 1 and result["items"][0]["id"] == item.id
    empty = service.search(db, users["viewer"], tool="radare2", language="python", page=2, page_size=1)
    assert empty["total"] == 1 and not empty["items"]


def test_input_validation_rejects_invalid_document_date_and_url():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        s.TemplateImport(
            name="Invalid",
            document={"schema_version": 1, "sections": [{"id": "same", "title": "A"}, {"id": "same", "title": "B"}]},
        )
    with pytest.raises(ValidationError):
        s.CompetitionCreate(name="Invalid", url="javascript:alert(1)")
    with pytest.raises(ValidationError):
        s.CompetitionCreate(name="Invalid", start_at="2026-01-01T00:00:00")
    with pytest.raises(ValidationError):
        s.ChallengeCreate(name="Invalid", references=["file:///etc/passwd"])


@pytest.fixture
def workspace_client(workspace):
    from app.db import get_db
    from app.modules.workspace.routes import router

    db, users, team = workspace
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    def override_db():
        try:
            yield db
        except Exception:
            db.rollback()
            raise

    app.dependency_overrides[get_db] = override_db
    for role, user in users.items():
        db.add(
            m.SessionModel(
                user_id=user.id,
                token_hash=hashlib.sha256(f"session-{role}".encode()).hexdigest(),
                csrf_token=f"csrf-{role}",
                expires_at=service.now() + timedelta(hours=1),
            )
        )
    db.commit()
    with TestClient(app) as client:

        def login_as(role):
            client.cookies.set("ctf_session", f"session-{role}")
            client.headers["X-CSRF-Token"] = f"csrf-{role}"

        yield client, login_as, db, users, team


def test_api_requires_session_csrf_and_returns_paginated_safe_data(workspace_client):
    client, login_as, db, users, team = workspace_client
    assert client.get("/api/v1/competitions").status_code == 401
    login_as("owner")
    del client.headers["X-CSRF-Token"]
    assert client.post("/api/v1/competitions", json={"name": "Bloqueado"}).status_code == 403
    client.headers["X-CSRF-Token"] = "csrf-owner"
    created = client.post("/api/v1/competitions", json={"name": "API", "team_id": team.id, "visibility": "team"})
    assert created.status_code == 201
    login_as("viewer")
    response = client.get("/api/v1/competitions?page=1&page_size=1")
    assert response.status_code == 200 and response.json()["total"] == 1
    members = client.get(f"/api/v1/teams/{team.id}/members").json()
    assert "password_hash" not in str(members)
    assert (
        client.patch(
            f"/api/v1/competitions/{created.json()['id']}", json={"name": "Sem permissão", "expected_version": 1}
        ).status_code
        == 403
    )
    assert client.get("/api/v1/search?date_from=2026-01-01T00:00:00").status_code == 422


def test_api_admin_user_safety_revocation_and_settings(workspace_client):
    client, login_as, db, users, team = workspace_client
    login_as("owner")
    assert client.get("/api/v1/admin/users").status_code == 403
    login_as("admin")
    listing = client.get("/api/v1/admin/users").json()
    assert "password_hash" not in str(listing)
    assert client.patch(f"/api/v1/admin/users/{users['admin'].id}", json={"is_admin": False}).status_code == 409
    settings = client.patch("/api/v1/admin/settings", json={"registration_enabled": False, "retention_days": 90})
    assert settings.status_code == 200 and settings.json()["registration_enabled"] is False
    disabled = client.patch(f"/api/v1/admin/users/{users['outsider'].id}", json={"is_active": False})
    assert disabled.status_code == 200
    db.expire_all()
    assert (
        db.scalar(select(m.SessionModel).where(m.SessionModel.user_id == users["outsider"].id)).revoked_at is not None
    )
    login_as("outsider")
    assert client.get("/api/v1/dashboard").status_code == 401


def test_notification_owner_only_read(workspace_client):
    client, login_as, db, users, team = workspace_client
    service.notify(db, users["owner"].id, "test", "Privada", team.id)
    db.commit()
    item = db.scalar(select(m.Notification).where(m.Notification.user_id == users["owner"].id))
    login_as("viewer")
    assert client.patch(f"/api/v1/notifications/{item.id}", json={"read": True}).status_code == 404
    login_as("owner")
    response = client.patch(f"/api/v1/notifications/{item.id}", json={"read": True})
    assert response.status_code == 200 and response.json()["read_at"]


def test_real_concurrent_cas_does_not_overwrite(workspace):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    db, users, team = workspace
    item = team_competition(db, users["owner"], team)
    engine = db.bind
    actor_id = users["owner"].id
    barrier = Barrier(2)

    def save(name):
        with Session(engine, expire_on_commit=False) as separate:
            actor = separate.get(m.User, actor_id)
            barrier.wait(timeout=10)
            try:
                return service.patch_competition(
                    separate, actor, item["id"], s.CompetitionPatch(expected_version=1, name=name)
                )["name"]
            except HTTPException as error:
                assert error.status_code == 409
                return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(save, ["Edição A", "Edição B"]))
    assert results.count("conflict") == 1
    db.expire_all()
    assert db.get(m.Competition, item["id"]).version == 2
    assert db.get(m.Competition, item["id"]).name in results


def test_admin_services_revoke_sessions_and_protect_last_managers(workspace):
    db, users, team = workspace
    expect_http(403, lambda: service.read_settings(db, users["owner"]))
    expect_http(
        409, lambda: service.update_admin_user(db, users["admin"], users["admin"].id, s.AdminUserPatch(is_active=False))
    )
    service.set_member(db, users["owner"], team.id, users["manager"].id, "viewer")
    expect_http(
        409, lambda: service.update_admin_user(db, users["admin"], users["owner"].id, s.AdminUserPatch(is_active=False))
    )
    db.add(
        m.SessionModel(
            user_id=users["outsider"].id,
            token_hash="d" * 64,
            csrf_token="csrf",
            expires_at=service.now() + timedelta(hours=1),
        )
    )
    db.commit()
    response = service.update_admin_user(db, users["admin"], users["outsider"].id, s.AdminUserPatch(is_active=False))
    assert response["is_active"] is False and "password_hash" not in response
    assert db.scalar(select(m.SessionModel).where(m.SessionModel.user_id == users["outsider"].id)).revoked_at
    updated = service.patch_settings(db, users["admin"], s.SettingsPatch(registration_enabled=False, retention_days=90))
    assert updated["registration_enabled"] is False and updated["retention_days"] == 90
    assert service.patch_settings(db, users["admin"], s.SettingsPatch(retention_days=120))["retention_days"] == 120
    expect_http(422, lambda: service.patch_settings(db, users["admin"], s.SettingsPatch(ai_enabled=None)))


def test_services_category_team_notification_and_validation(workspace):
    db, users, team = workspace
    expect_http(403, lambda: service.patch_team(db, users["viewer"], team.id, s.TeamPatch(name="Sem permissão")))
    assert service.patch_team(db, users["owner"], team.id, s.TeamPatch(name="Nome novo"))["name"] == "Nome novo"
    expect_http(422, lambda: service.patch_team(db, users["owner"], team.id, s.TeamPatch(name=None)))
    category = service.create_category(
        db, users["editor"], s.CategoryCreate(name="Categoria de equipe", team_id=team.id)
    )
    assert category["team_id"] == team.id
    expect_http(
        409,
        lambda: service.create_category(
            db, users["editor"], s.CategoryCreate(name="Categoria de equipe", team_id=team.id)
        ),
    )
    expect_http(
        403, lambda: service.create_category(db, users["viewer"], s.CategoryCreate(name="Bloqueada", team_id=team.id))
    )
    service.notify(db, users["owner"].id, "test", "Restrita", team.id)
    db.commit()
    item = db.scalar(select(m.Notification).where(m.Notification.user_id == users["owner"].id))
    expect_http(404, lambda: service.read_notification(db, users["viewer"], item.id, True))
    assert service.read_notification(db, users["owner"], item.id, True)["read_at"]
    assert service.read_notification(db, users["owner"], item.id, False)["read_at"] is None
    competition = team_competition(db, users["owner"], team)
    expect_http(
        422,
        lambda: service.patch_competition(
            db, users["owner"], competition["id"], s.CompetitionPatch(expected_version=1, url="javascript:alert(1)")
        ),
    )
    assert db.get(m.Competition, competition["id"]).version == 1


def test_seed_idempotent_and_reviewer_decision_single_use(workspace):
    db, users, team = workspace
    service.seed_workspace(db)
    assert len(db.scalars(select(m.WriteupTemplate)).all()) == 10
    assert len(db.scalars(select(m.TemplateRevision)).all()) == 10
    item = team_writeup(db, users["owner"], team)
    created = service.create_review(db, users["owner"], item.id, s.ReviewCreate(reviewer_id=users["reviewer"].id))
    expect_http(
        409,
        lambda: service.create_review(db, users["owner"], item.id, s.ReviewCreate(reviewer_id=users["reviewer"].id)),
    )
    result = service.decide_review(db, users["reviewer"], created["id"], s.ReviewDecision(decision="changes_requested"))
    assert result["status"] == "changes_requested"
    expect_http(
        409, lambda: service.decide_review(db, users["reviewer"], created["id"], s.ReviewDecision(decision="approved"))
    )


def test_competition_participants_scoped_and_cleanup_on_team_departure(workspace):
    db, users, team = workspace
    item = team_competition(db, users["owner"], team)
    expect_http(
        422, lambda: service.set_competition_member(db, users["owner"], item["id"], users["outsider"].id, "participant")
    )
    service.set_competition_member(db, users["editor"], item["id"], users["viewer"].id, "participant")
    result = service.set_competition_member(db, users["owner"], item["id"], users["viewer"].id, "captain")
    assert result["role"] == "captain" and "password_hash" not in result["user"]
    listing = service.competition_members(db, users["viewer"], item["id"])
    assert listing["total"] == 1
    service.remove_member(db, users["owner"], team.id, users["viewer"].id)
    assert not db.scalar(select(m.CompetitionMember.id).where(m.CompetitionMember.user_id == users["viewer"].id))
    expect_http(404, lambda: service.remove_competition_member(db, users["owner"], item["id"], users["viewer"].id))
    service.set_competition_member(db, users["owner"], item["id"], users["editor"].id, "participant")
    assert service.remove_competition_member(db, users["owner"], item["id"], users["editor"].id)["ok"]
