# SPDX-License-Identifier: MIT
"""HTTP adapters: validation/auth dependencies, services, bounded pagination."""

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app import models as m
from app.db import get_db
from app.security import authorize_team, get_actor, require_csrf
from . import schemas as s
from . import services as service

router = APIRouter(tags=["Workspace"])
DB = Annotated[Session, Depends(get_db)]
Actor = Annotated[m.User, Depends(get_actor)]
MutationActor = Annotated[m.User, Depends(require_csrf)]
Page = Annotated[int, Query(ge=1, le=10000)]
PageSize = Annotated[int, Query(ge=1, le=100)]


@router.get("/dashboard")
def dashboard(db: DB, actor: Actor):
    return service.dashboard(db, actor)


@router.get("/competitions")
def competitions(
    db: DB,
    actor: Actor,
    page: Page = 1,
    page_size: PageSize = 25,
    q: str | None = Query(default=None, max_length=200),
    status: str | None = None,
):
    return service.list_resources(db, actor, m.Competition, page, page_size, q=q, status=status)


@router.post("/competitions", status_code=201)
def create_competition(payload: s.CompetitionCreate, db: DB, actor: MutationActor):
    return service.create_competition(db, actor, payload)


@router.get("/competitions/{resource_id}")
def get_competition(resource_id: str, db: DB, actor: Actor):
    return service.fields(service.resource(db, actor, m.Competition, resource_id))


@router.patch("/competitions/{resource_id}")
def patch_competition(resource_id: str, payload: s.CompetitionPatch, db: DB, actor: MutationActor):
    return service.patch_competition(db, actor, resource_id, payload)


@router.delete("/competitions/{resource_id}")
def delete_competition(resource_id: str, db: DB, actor: MutationActor, expected_version: int = Query(ge=1)):
    return service.soft_delete(db, actor, m.Competition, resource_id, expected_version)


@router.get("/challenges")
def challenges(
    db: DB,
    actor: Actor,
    page: Page = 1,
    page_size: PageSize = 25,
    q: str | None = Query(default=None, max_length=200),
    status: str | None = None,
    category: str | None = None,
    competition_id: str | None = None,
):
    return service.list_resources(
        db, actor, m.Challenge, page, page_size, q=q, status=status, category=category, competition_id=competition_id
    )


@router.get("/competitions/{resource_id}/members")
def competition_members(resource_id: str, db: DB, actor: Actor):
    return service.competition_members(db, actor, resource_id)


@router.post("/competitions/{resource_id}/members", status_code=201)
def add_competition_member(resource_id: str, payload: s.CompetitionParticipant, db: DB, actor: MutationActor):
    return service.set_competition_member(db, actor, resource_id, payload.user_id, payload.role)


@router.delete("/competitions/{resource_id}/members/{user_id}")
def delete_competition_member(resource_id: str, user_id: str, db: DB, actor: MutationActor):
    return service.remove_competition_member(db, actor, resource_id, user_id)


@router.post("/challenges", status_code=201)
def create_challenge(payload: s.ChallengeCreate, db: DB, actor: MutationActor):
    return service.create_challenge(db, actor, payload)


@router.get("/challenges/{resource_id}")
def get_challenge(resource_id: str, db: DB, actor: Actor):
    return service.challenge_output(db, service.resource(db, actor, m.Challenge, resource_id))


@router.patch("/challenges/{resource_id}")
def patch_challenge(resource_id: str, payload: s.ChallengePatch, db: DB, actor: MutationActor):
    return service.patch_challenge(db, actor, resource_id, payload)


@router.delete("/challenges/{resource_id}")
def delete_challenge(resource_id: str, db: DB, actor: MutationActor, expected_version: int = Query(ge=1)):
    return service.soft_delete(db, actor, m.Challenge, resource_id, expected_version)


@router.get("/categories")
def categories(db: DB, actor: Actor, page: Page = 1, page_size: PageSize = 100):
    memberships = select(m.TeamMember.team_id).where(m.TeamMember.user_id == actor.id)
    query = select(m.Category)
    if not actor.is_admin:
        query = query.where(
            or_(
                and_(m.Category.owner_id.is_(None), m.Category.team_id.is_(None)),
                m.Category.owner_id == actor.id,
                m.Category.team_id.in_(memberships),
            )
        )
    return service.page_result(db, query.order_by(m.Category.name, m.Category.id), page, page_size)


@router.post("/categories", status_code=201)
def create_category(payload: s.CategoryCreate, db: DB, actor: MutationActor):
    return service.create_category(db, actor, payload)


@router.get("/teams")
def teams(db: DB, actor: Actor, page: Page = 1, page_size: PageSize = 25):
    return service.list_teams(db, actor, page, page_size)


@router.post("/teams", status_code=201)
def create_team(payload: s.TeamCreate, db: DB, actor: MutationActor):
    return service.create_team(db, actor, payload)


@router.post("/teams/invites/accept")
def accept_invite(payload: s.AcceptInvite, db: DB, actor: MutationActor):
    return service.accept_invite(db, actor, payload.token)


@router.get("/teams/{team_id}")
def get_team(team_id: str, db: DB, actor: Actor):
    return service.fields(authorize_team(db, actor, team_id))


@router.patch("/teams/{team_id}")
def patch_team(team_id: str, payload: s.TeamPatch, db: DB, actor: MutationActor):
    return service.patch_team(db, actor, team_id, payload)


@router.get("/teams/{team_id}/members")
def members(team_id: str, db: DB, actor: Actor):
    return service.team_members(db, actor, team_id)


@router.post("/teams/{team_id}/members", status_code=201)
def add_member(team_id: str, payload: s.MemberInput, db: DB, actor: MutationActor):
    return service.set_member(db, actor, team_id, payload.user_id, payload.role)


@router.patch("/teams/{team_id}/members/{user_id}")
def patch_member(team_id: str, user_id: str, payload: s.MemberPatch, db: DB, actor: MutationActor):
    return service.set_member(db, actor, team_id, user_id, payload.role)


@router.delete("/teams/{team_id}/members/{user_id}")
def delete_member(team_id: str, user_id: str, db: DB, actor: MutationActor):
    return service.remove_member(db, actor, team_id, user_id)


@router.post("/teams/{team_id}/invites", status_code=201)
def invite(team_id: str, payload: s.InviteInput, db: DB, actor: MutationActor):
    return service.create_invite(db, actor, team_id, payload)


@router.get("/users")
def users(db: DB, actor: Actor, page: Page = 1, page_size: PageSize = 25):
    query = select(m.User).where(m.User.is_active.is_(True))
    if not actor.is_admin:
        teams = select(m.TeamMember.team_id).where(m.TeamMember.user_id == actor.id)
        ids = select(m.TeamMember.user_id).where(m.TeamMember.team_id.in_(teams))
        query = query.where(or_(m.User.id == actor.id, m.User.id.in_(ids)))
    return service.page_result(db, query.order_by(m.User.name), page, page_size, service.public_user)


@router.get("/templates")
def templates(db: DB, actor: Actor, page: Page = 1, page_size: PageSize = 25):
    return service.page_result(db, service.templates_query(db, actor).order_by(m.WriteupTemplate.name), page, page_size)


@router.post("/templates", status_code=201)
def create_template(payload: s.TemplateCreate, db: DB, actor: MutationActor):
    return service.create_template(db, actor, payload)


@router.post("/templates/import", status_code=201)
def import_template(payload: s.TemplateImport, db: DB, actor: MutationActor):
    return service.create_template(db, actor, payload)


@router.get("/templates/{template_id}")
def get_template(template_id: str, db: DB, actor: Actor):
    return service.fields(service.template_resource(db, actor, template_id))


@router.patch("/templates/{template_id}")
def patch_template(template_id: str, payload: s.TemplatePatch, db: DB, actor: MutationActor):
    return service.patch_template(db, actor, template_id, payload)


@router.get("/templates/{template_id}/revisions")
def template_revisions(template_id: str, db: DB, actor: Actor, page: Page = 1, page_size: PageSize = 25):
    service.template_resource(db, actor, template_id)
    return service.page_result(
        db,
        select(m.TemplateRevision)
        .where(m.TemplateRevision.template_id == template_id)
        .order_by(m.TemplateRevision.version.desc()),
        page,
        page_size,
    )


@router.get("/templates/{template_id}/export")
def export_template(template_id: str, db: DB, actor: Actor):
    item = service.template_resource(db, actor, template_id)
    return {"schema_version": 1, "name": item.name, "description": item.description, "document": item.document}


@router.get("/writeups/{writeup_id}/comments")
def comments(writeup_id: str, db: DB, actor: Actor, page: Page = 1, page_size: PageSize = 25):
    service.resource(db, actor, m.Writeup, writeup_id)
    return service.page_result(
        db, select(m.Comment).where(m.Comment.writeup_id == writeup_id).order_by(m.Comment.created_at), page, page_size
    )


@router.post("/writeups/{writeup_id}/comments", status_code=201)
def create_comment(writeup_id: str, payload: s.CommentCreate, db: DB, actor: MutationActor):
    return service.create_comment(db, actor, writeup_id, payload)


@router.patch("/comments/{comment_id}")
def resolve_comment(comment_id: str, payload: s.CommentPatch, db: DB, actor: MutationActor):
    return service.resolve_comment(db, actor, comment_id, payload.resolved)


@router.get("/writeups/{writeup_id}/reviews")
def reviews(writeup_id: str, db: DB, actor: Actor, page: Page = 1, page_size: PageSize = 25):
    service.resource(db, actor, m.Writeup, writeup_id)
    return service.page_result(
        db,
        select(m.ReviewRequest)
        .where(m.ReviewRequest.writeup_id == writeup_id)
        .order_by(m.ReviewRequest.created_at.desc()),
        page,
        page_size,
    )


@router.post("/writeups/{writeup_id}/reviews", status_code=201)
def create_review(writeup_id: str, payload: s.ReviewCreate, db: DB, actor: MutationActor):
    return service.create_review(db, actor, writeup_id, payload)


@router.post("/reviews/{review_id}/decision")
def decide_review(review_id: str, payload: s.ReviewDecision, db: DB, actor: MutationActor):
    return service.decide_review(db, actor, review_id, payload)


@router.get("/notifications")
def notifications(db: DB, actor: Actor, page: Page = 1, page_size: PageSize = 25, unread: bool = False):
    query = select(m.Notification).where(m.Notification.user_id == actor.id)
    if unread:
        query = query.where(m.Notification.read_at.is_(None))
    return service.page_result(db, query.order_by(m.Notification.created_at.desc()), page, page_size)


@router.patch("/notifications/{notification_id}")
def read_notification(notification_id: str, payload: s.NotificationPatch, db: DB, actor: MutationActor):
    return service.read_notification(db, actor, notification_id, payload.read)


@router.get("/audit")
def audit_logs(db: DB, actor: Actor, page: Page = 1, page_size: PageSize = 25, action: str | None = None):
    query = select(m.AuditLog)
    if not actor.is_admin:
        query = query.where(m.AuditLog.actor_id == actor.id)
    if action:
        query = query.where(m.AuditLog.action == action)
    return service.page_result(db, query.order_by(m.AuditLog.created_at.desc()), page, page_size)


@router.get("/search")
def search(
    db: DB,
    actor: Actor,
    q: str = Query(default="", max_length=300),
    category: str | None = Query(default=None, max_length=80),
    tags: str | None = Query(default=None, max_length=2000),
    author_id: str | None = None,
    tool: str | None = Query(default=None, max_length=80),
    language: str | None = Query(default=None, max_length=80),
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    sort: Literal["recent", "oldest", "name"] = "recent",
    page: Page = 1,
    page_size: PageSize = 25,
):
    if any(value is not None and value.tzinfo is None for value in (date_from, date_to)):
        raise HTTPException(422, "Filtros de data devem incluir fuso horário")
    if date_from and date_to and date_to < date_from:
        raise HTTPException(422, "Período de busca inválido")
    return service.search(
        db,
        actor,
        q=q,
        category=category,
        tags=tags,
        author_id=author_id,
        tool=tool,
        language=language,
        date_from=date_from,
        date_to=date_to,
        sort=sort,
        page=page,
        page_size=page_size,
    )


@router.get("/admin/users")
def admin_users(db: DB, actor: Actor, page: Page = 1, page_size: PageSize = 25):
    service.require_admin(actor)
    return service.page_result(
        db, select(m.User).order_by(m.User.created_at.desc()), page, page_size, service.public_user
    )


@router.patch("/admin/users/{user_id}")
def admin_user(user_id: str, payload: s.AdminUserPatch, db: DB, actor: MutationActor):
    return service.update_admin_user(db, actor, user_id, payload)


@router.get("/admin/settings")
def admin_settings(db: DB, actor: Actor):
    return service.read_settings(db, actor)


@router.patch("/admin/settings")
def patch_settings(payload: s.SettingsPatch, db: DB, actor: MutationActor):
    return service.patch_settings(db, actor, payload)
