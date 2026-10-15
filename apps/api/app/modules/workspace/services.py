# SPDX-License-Identifier: MIT
from datetime import datetime, timedelta, timezone
import hashlib
import secrets
from uuid import NAMESPACE_URL, uuid5

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import String, and_, cast, delete, func, literal, literal_column, or_, select, union_all, update

from app import models as m
from app.schemas import Document
from app.security import audit, authorize, authorize_team, visible_query
from .repositories import atomic_update, paginated
from .schemas import ChallengeCreate, CompetitionCreate


def now():
    return datetime.now(timezone.utc)


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value and value.tzinfo is None else value


def fields(obj):
    return {column.name: getattr(obj, column.name) for column in obj.__table__.columns}


def validated_input(schema, values):
    try:
        return schema.model_validate(values).model_dump()
    except ValidationError as error:
        raise HTTPException(422, "; ".join(item["msg"] for item in error.errors())) from error


def public_user(user):
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "is_admin": user.is_admin,
        "is_active": user.is_active,
    }


def require_admin(actor):
    if not actor.is_admin:
        raise HTTPException(403, "Acesso administrativo necessário")


def resource(db, actor, model, resource_id, action="read"):
    item = db.get(model, resource_id)
    if not item or getattr(item, "deleted_at", None):
        raise HTTPException(404, "Recurso não encontrado")
    authorize(db, actor, item, action)
    return item


def page_result(db, statement, page=1, page_size=25, serializer=fields):
    rows, total = paginated(db, statement, page, page_size)
    return {"items": [serializer(row) for row in rows], "total": total, "page": page, "page_size": page_size}


def list_resources(db, actor, model, page, page_size, q=None, status=None, category=None, competition_id=None):
    statement = visible_query(select(model), model, actor, db)
    if hasattr(model, "deleted_at"):
        statement = statement.where(model.deleted_at.is_(None))
    if q:
        statement = statement.where(model.name.ilike(f"%{q}%"))
    if status:
        statement = statement.where(model.status == status)
    if category and hasattr(model, "category"):
        statement = statement.where(model.category == category)
    if competition_id and hasattr(model, "competition_id"):
        statement = statement.where(model.competition_id == competition_id)
    return page_result(db, statement.order_by(model.created_at.desc(), model.id), page, page_size)


def validate_scope(db, actor, data, existing=None):
    team_id = data.get("team_id")
    if team_id:
        authorize_team(db, actor, team_id, "write")
    if data.get("visibility") == "team" and not team_id:
        raise HTTPException(422, "Visibilidade de equipe exige team_id")
    if existing and existing.team_id != team_id:
        if isinstance(existing, m.Competition) and db.scalar(
            select(m.CompetitionMember.id).where(m.CompetitionMember.competition_id == existing.id).limit(1)
        ):
            raise HTTPException(409, "Retire os participantes antes de transferir a competição")
        linked_models = (
            (m.Challenge, m.Writeup, m.Evidence) if isinstance(existing, m.Competition) else (m.Writeup, m.Evidence)
        )
        for model in linked_models:
            fk_name = "competition_id" if isinstance(existing, m.Competition) else "challenge_id"
            if hasattr(model, fk_name) and db.scalar(
                select(model.id).where(getattr(model, fk_name) == existing.id).limit(1)
            ):
                raise HTTPException(409, "Não altere a equipe de um recurso que possui vínculos")
    if existing and existing.visibility == "team" and data.get("visibility") == "private":
        related_models = (m.Challenge,) if isinstance(existing, m.Competition) else (m.Writeup, m.Evidence)
        fk_name = "competition_id" if isinstance(existing, m.Competition) else "challenge_id"
        for model in related_models:
            if db.scalar(
                select(model.id)
                .where(getattr(model, fk_name) == existing.id, model.visibility == "team", model.deleted_at.is_(None))
                .limit(1)
            ):
                raise HTTPException(409, "Retire o compartilhamento dos recursos associados primeiro")


def validate_competition(db, actor, values):
    competition_id = values.get("competition_id")
    if not competition_id:
        return
    parent = resource(db, actor, m.Competition, competition_id, "read")
    if values.get("team_id") != parent.team_id:
        raise HTTPException(422, "Desafio e competição devem pertencer ao mesmo espaço de trabalho")
    if values.get("visibility") == "team" and parent.visibility != "team":
        raise HTTPException(422, "Competição privada não aceita desafio compartilhado")
    authorize(db, actor, parent, "write")


INITIAL_CATEGORIES = [
    "Web",
    "Pwn",
    "Reverse Engineering",
    "Cryptography",
    "Forensics",
    "OSINT",
    "Misc",
    "Mobile",
    "Cloud",
    "Active Directory",
]
SECTION_TITLES = [
    "Informações do desafio",
    "Objetivo",
    "Contexto",
    "Ambiente",
    "Reconhecimento e análise",
    "Hipóteses",
    "Metodologia utilizada",
    "Etapas técnicas",
    "Comandos executados",
    "Resultados observados",
    "Evidências",
    "Exploração ou resolução do desafio",
    "Validação",
    "Flag",
    "Conclusão",
    "Lições aprendidas",
    "Referências",
]
TEMPLATE_NAMES = [
    "CTF Writeup",
    "Hack The Box",
    "TryHackMe",
    "PicoCTF",
    "Pentest Report",
    "Vulnerability Report",
    "CVE Research Report",
    "Bug Bounty Report",
    "Forensic Analysis",
    "Reverse Engineering Report",
]


def seed_workspace(db):
    """Seeds determinísticos, idempotentes e sem conteúdo técnico fabricado."""
    for name in INITIAL_CATEGORIES:
        category_id = str(uuid5(NAMESPACE_URL, f"ctf-studio/category/{name}"))
        if not db.get(m.Category, category_id):
            db.add(m.Category(id=category_id, name=name, owner_id=None, team_id=None))
    for name in TEMPLATE_NAMES:
        template_id = str(uuid5(NAMESPACE_URL, f"ctf-studio/template/{name}"))
        if not db.get(m.WriteupTemplate, template_id):
            titles = (
                SECTION_TITLES
                if name in TEMPLATE_NAMES[:4]
                else [
                    "Resumo executivo",
                    "Escopo",
                    "Ambiente",
                    "Metodologia",
                    "Observações confirmadas",
                    "Hipóteses",
                    "Evidências",
                    "Análise técnica",
                    "Impacto",
                    "Recomendações",
                    "Validação",
                    "Conclusão",
                    "Referências",
                ]
            )
            document = Document.model_validate(
                {
                    "schema_version": 1,
                    "sections": [
                        {"id": f"section-{index + 1}", "title": title, "markdown": ""}
                        for index, title in enumerate(titles)
                    ],
                }
            ).model_dump()
            db.add(
                m.WriteupTemplate(
                    id=template_id,
                    name=name,
                    description="Modelo editável; preencha somente com observações e evidências reais.",
                    document=document,
                    owner_id=None,
                    team_id=None,
                    version=1,
                )
            )
            db.flush()
            db.add(
                m.TemplateRevision(
                    template_id=template_id,
                    version=1,
                    name=name,
                    description="Modelo padrão",
                    document=document,
                    author_id=None,
                )
            )
    db.commit()


def validate_category(db, actor, name, team_id):
    statement = select(m.Category).where(m.Category.name == name)
    candidates = db.scalars(statement).all()
    if not any(
        (item.owner_id is None and item.team_id is None)
        or item.owner_id == actor.id
        or (team_id is not None and item.team_id == team_id)
        for item in candidates
    ):
        raise HTTPException(422, "Categoria não disponível; cadastre uma categoria personalizada")


def set_assignees(db, actor, challenge, user_ids):
    distinct = list(dict.fromkeys(user_ids))
    for user_id in distinct:
        user = db.get(m.User, user_id)
        if not user or not user.is_active:
            raise HTTPException(422, "Responsável inválido")
        if challenge.team_id:
            if not db.scalar(
                select(m.TeamMember).where(m.TeamMember.team_id == challenge.team_id, m.TeamMember.user_id == user_id)
            ):
                raise HTTPException(422, "Responsável deve participar da equipe")
        elif user_id != challenge.owner_id:
            raise HTTPException(422, "Desafio privado só pode ser atribuído ao proprietário")
    db.execute(delete(m.ChallengeAssignment).where(m.ChallengeAssignment.challenge_id == challenge.id))
    for user_id in distinct:
        db.add(m.ChallengeAssignment(challenge_id=challenge.id, user_id=user_id, assigned_by=actor.id))


def competition_members(db, actor, competition_id):
    resource(db, actor, m.Competition, competition_id)
    rows = db.execute(
        select(m.CompetitionMember, m.User)
        .join(m.User, m.User.id == m.CompetitionMember.user_id)
        .where(m.CompetitionMember.competition_id == competition_id)
        .order_by(m.User.name)
    ).all()
    return {
        "items": [{"user_id": user.id, "role": member.role, "user": public_user(user)} for member, user in rows],
        "total": len(rows),
        "page": 1,
        "page_size": len(rows) or 1,
    }


def set_competition_member(db, actor, competition_id, user_id, role):
    item = resource(db, actor, m.Competition, competition_id, "write")
    user = db.get(m.User, user_id)
    if not user or not user.is_active:
        raise HTTPException(422, "Participante inválido")
    if item.visibility == "team":
        if not db.scalar(
            select(m.TeamMember.id).where(m.TeamMember.team_id == item.team_id, m.TeamMember.user_id == user_id)
        ):
            raise HTTPException(422, "Participante deve ser membro da equipe")
    elif user.id != item.owner_id:
        raise HTTPException(422, "Competição privada só pode incluir seu proprietário")
    member = db.scalar(
        select(m.CompetitionMember).where(
            m.CompetitionMember.competition_id == item.id, m.CompetitionMember.user_id == user_id
        )
    )
    if member:
        member.role = role
    else:
        db.add(m.CompetitionMember(competition_id=item.id, user_id=user_id, role=role))
    audit(db, actor, "competition.member.updated", "competition", item.id, {"user_id": user_id, "role": role})
    db.commit()
    return {"user_id": user.id, "role": role, "user": public_user(user)}


def remove_competition_member(db, actor, competition_id, user_id):
    item = resource(db, actor, m.Competition, competition_id, "write")
    result = db.execute(
        delete(m.CompetitionMember).where(
            m.CompetitionMember.competition_id == item.id, m.CompetitionMember.user_id == user_id
        )
    )
    if result.rowcount != 1:
        raise HTTPException(404, "Participante não encontrado")
    audit(db, actor, "competition.member.removed", "competition", item.id, {"user_id": user_id})
    db.commit()
    return {"ok": True}


def challenge_output(db, item):
    output = fields(item)
    output["assignee_ids"] = list(
        db.scalars(select(m.ChallengeAssignment.user_id).where(m.ChallengeAssignment.challenge_id == item.id))
    )
    return output


def create_competition(db, actor, payload):
    values = payload.model_dump()
    validate_scope(db, actor, values)
    item = m.Competition(owner_id=actor.id, **values)
    db.add(item)
    db.flush()
    audit(db, actor, "competition.created", "competition", item.id)
    db.commit()
    return fields(item)


def patch_competition(db, actor, resource_id, payload):
    item = resource(db, actor, m.Competition, resource_id, "write")
    change = payload.model_dump(exclude_unset=True)
    expected = change.pop("expected_version")
    values = {key: getattr(item, key) for key in CompetitionCreate.model_fields}
    values.update(change)
    values = validated_input(CompetitionCreate, values)
    validate_scope(db, actor, values, item)
    updated = atomic_update(db, m.Competition, item.id, expected, {**values, "updated_at": now()})
    audit(db, actor, "competition.updated", "competition", item.id, {"version": expected + 1})
    db.commit()
    return fields(updated)


def create_challenge(db, actor, payload):
    values = payload.model_dump()
    assignees = values.pop("assignee_ids")
    validate_scope(db, actor, values)
    validate_competition(db, actor, values)
    validate_category(db, actor, values["category"], values.get("team_id"))
    item = m.Challenge(owner_id=actor.id, **values)
    db.add(item)
    db.flush()
    set_assignees(db, actor, item, assignees)
    audit(db, actor, "challenge.created", "challenge", item.id)
    db.commit()
    return challenge_output(db, item)


def patch_challenge(db, actor, resource_id, payload):
    item = resource(db, actor, m.Challenge, resource_id, "write")
    changes = payload.model_dump(exclude_unset=True)
    expected = changes.pop("expected_version")
    values = {key: getattr(item, key) for key in ChallengeCreate.model_fields if key != "assignee_ids"}
    values["assignee_ids"] = challenge_output(db, item)["assignee_ids"]
    values.update(changes)
    validated = validated_input(ChallengeCreate, values)
    assignees = validated.pop("assignee_ids")
    validate_scope(db, actor, validated, item)
    validate_competition(db, actor, validated)
    validate_category(db, actor, validated["category"], validated.get("team_id"))
    result = atomic_update(db, m.Challenge, item.id, expected, {**validated, "updated_at": now()})
    set_assignees(db, actor, result, assignees)
    audit(db, actor, "challenge.updated", "challenge", item.id, {"version": expected + 1})
    db.commit()
    return challenge_output(db, result)


def soft_delete(db, actor, model, resource_id, expected_version):
    item = resource(db, actor, model, resource_id, "delete")
    related_models = (m.Challenge,) if model is m.Competition else (m.Writeup, m.Evidence)
    fk_name = "competition_id" if model is m.Competition else "challenge_id"
    for related in related_models:
        if db.scalar(
            select(related.id).where(getattr(related, fk_name) == item.id, related.deleted_at.is_(None)).limit(1)
        ):
            raise HTTPException(409, "Remova ou desvincule os recursos associados antes de excluir")
    atomic_update(db, model, item.id, expected_version, {"deleted_at": now(), "updated_at": now()})
    audit(db, actor, f"{model.__tablename__}.deleted", model.__tablename__, item.id)
    db.commit()
    return {"ok": True}


def list_teams(db, actor, page, page_size):
    query = select(m.Team)
    if not actor.is_admin:
        memberships = select(m.TeamMember.team_id).where(m.TeamMember.user_id == actor.id)
        query = query.where(or_(m.Team.id.in_(memberships), m.Team.owner_id == actor.id))
    return page_result(db, query.order_by(m.Team.created_at.desc()), page, page_size)


def create_team(db, actor, payload):
    team = m.Team(owner_id=actor.id, **payload.model_dump())
    db.add(team)
    db.flush()
    db.add(m.TeamMember(team_id=team.id, user_id=actor.id, role="manager"))
    audit(db, actor, "team.created", "team", team.id)
    db.commit()
    return fields(team)


def patch_team(db, actor, team_id, payload):
    item = authorize_team(db, actor, team_id, "manage")
    for name, value in payload.model_dump(exclude_unset=True).items():
        if value is None:
            raise HTTPException(422, "Nome e descrição não podem ser nulos")
        setattr(item, name, value)
    audit(db, actor, "team.updated", "team", item.id)
    db.commit()
    return fields(item)


def create_category(db, actor, payload):
    if payload.team_id:
        authorize_team(db, actor, payload.team_id, "write")
    duplicate = db.scalar(
        select(m.Category.id).where(
            m.Category.name == payload.name, m.Category.team_id == payload.team_id, m.Category.owner_id == actor.id
        )
    )
    if duplicate:
        raise HTTPException(409, "Categoria já cadastrada")
    item = m.Category(owner_id=actor.id, **payload.model_dump())
    db.add(item)
    db.flush()
    audit(db, actor, "category.created", "category", item.id)
    db.commit()
    return fields(item)


def team_members(db, actor, team_id):
    authorize_team(db, actor, team_id)
    rows = db.execute(
        select(m.TeamMember, m.User)
        .join(m.User, m.User.id == m.TeamMember.user_id)
        .where(m.TeamMember.team_id == team_id)
        .order_by(m.User.name)
    ).all()
    return {
        "items": [
            {"user_id": user.id, "role": membership.role, "user": public_user(user)} for membership, user in rows
        ],
        "total": len(rows),
        "page": 1,
        "page_size": len(rows) or 1,
    }


def manager_count(db, team_id):
    return (
        db.scalar(
            select(func.count())
            .select_from(m.TeamMember)
            .join(m.User, m.User.id == m.TeamMember.user_id)
            .where(m.TeamMember.team_id == team_id, m.TeamMember.role == "manager", m.User.is_active.is_(True))
        )
        or 0
    )


def set_member(db, actor, team_id, user_id, role):
    authorize_team(db, actor, team_id, "manage")
    # Bloqueio da equipe serializa a retirada simultânea dos últimos gestores.
    db.scalar(select(m.Team).where(m.Team.id == team_id).with_for_update())
    user = db.get(m.User, user_id)
    if not user or not user.is_active:
        raise HTTPException(404, "Usuário não encontrado")
    membership = db.scalar(select(m.TeamMember).where(m.TeamMember.team_id == team_id, m.TeamMember.user_id == user_id))
    if membership:
        if membership.role == "manager" and role != "manager" and manager_count(db, team_id) <= 1:
            raise HTTPException(409, "A equipe precisa manter pelo menos um gestor")
        membership.role = role
    else:
        membership = m.TeamMember(team_id=team_id, user_id=user_id, role=role)
        db.add(membership)
    audit(db, actor, "team.member.updated", "team", team_id, {"user_id": user_id, "role": role})
    db.commit()
    return {"user_id": user.id, "role": role, "user": public_user(user)}


def remove_member(db, actor, team_id, user_id):
    authorize_team(db, actor, team_id, "manage")
    db.scalar(select(m.Team).where(m.Team.id == team_id).with_for_update())
    membership = db.scalar(select(m.TeamMember).where(m.TeamMember.team_id == team_id, m.TeamMember.user_id == user_id))
    if not membership:
        raise HTTPException(404, "Membro não encontrado")
    if membership.role == "manager" and manager_count(db, team_id) <= 1:
        raise HTTPException(409, "A equipe precisa manter pelo menos um gestor")
    db.execute(
        delete(m.ChallengeAssignment).where(
            m.ChallengeAssignment.user_id == user_id,
            m.ChallengeAssignment.challenge_id.in_(select(m.Challenge.id).where(m.Challenge.team_id == team_id)),
        )
    )
    db.execute(
        delete(m.CompetitionMember).where(
            m.CompetitionMember.user_id == user_id,
            m.CompetitionMember.competition_id.in_(select(m.Competition.id).where(m.Competition.team_id == team_id)),
        )
    )
    db.delete(membership)
    audit(db, actor, "team.member.removed", "team", team_id, {"user_id": user_id})
    db.commit()
    return {"ok": True}


def create_invite(db, actor, team_id, payload):
    authorize_team(db, actor, team_id, "manage")
    token = secrets.token_urlsafe(32)
    invite = m.TeamInvite(
        team_id=team_id,
        email=payload.email,
        role=payload.role,
        token_hash=hashlib.sha256(token.encode()).hexdigest(),
        expires_at=now() + timedelta(days=7),
        created_by=actor.id,
    )
    db.add(invite)
    db.flush()
    audit(db, actor, "team.invite.created", "team", team_id, {"invite_id": invite.id, "role": payload.role})
    db.commit()
    return {
        "id": invite.id,
        "team_id": team_id,
        "email": invite.email,
        "role": invite.role,
        "token": token,
        "expires_at": invite.expires_at,
    }


def accept_invite(db, actor, token):
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    invite = db.scalar(select(m.TeamInvite).where(m.TeamInvite.token_hash == token_hash).with_for_update())
    if not invite or invite.accepted_at or aware(invite.expires_at) <= now():
        raise HTTPException(410, "Convite inválido ou expirado")
    if invite.email.lower() != actor.email.lower():
        raise HTTPException(403, "Este convite pertence a outro email")
    claimed = db.execute(
        update(m.TeamInvite)
        .where(m.TeamInvite.id == invite.id, m.TeamInvite.accepted_at.is_(None), m.TeamInvite.expires_at > now())
        .values(accepted_at=now())
        .execution_options(synchronize_session=False)
    )
    if claimed.rowcount != 1:
        db.rollback()
        raise HTTPException(410, "Convite já utilizado ou expirado")
    db.scalar(select(m.Team).where(m.Team.id == invite.team_id).with_for_update())
    membership = db.scalar(
        select(m.TeamMember).where(m.TeamMember.team_id == invite.team_id, m.TeamMember.user_id == actor.id)
    )
    # Aceitar um convite antigo nunca reduz nem amplia papel de quem já é membro.
    if not membership:
        db.add(m.TeamMember(team_id=invite.team_id, user_id=actor.id, role=invite.role))
    invite.accepted_at = now()
    audit(db, actor, "team.invite.accepted", "team", invite.team_id)
    db.commit()
    return {"team_id": invite.team_id, "role": membership.role if membership else invite.role}


def templates_query(db, actor):
    memberships = select(m.TeamMember.team_id).where(m.TeamMember.user_id == actor.id)
    query = select(m.WriteupTemplate)
    if not actor.is_admin:
        query = query.where(
            or_(
                and_(m.WriteupTemplate.owner_id.is_(None), m.WriteupTemplate.team_id.is_(None)),
                and_(m.WriteupTemplate.owner_id == actor.id, m.WriteupTemplate.visibility != "team"),
                and_(m.WriteupTemplate.visibility == "team", m.WriteupTemplate.team_id.in_(memberships)),
            )
        )
    if hasattr(m.WriteupTemplate, "deleted_at"):
        query = query.where(m.WriteupTemplate.deleted_at.is_(None))
    return query


def template_resource(db, actor, template_id, action="read"):
    item = db.get(m.WriteupTemplate, template_id)
    if not item or getattr(item, "deleted_at", None):
        raise HTTPException(404, "Template não encontrado")
    if item.owner_id is None and item.team_id is None:
        if action != "read" and not actor.is_admin:
            raise HTTPException(403, "Duplique o template padrão para personalizá-lo")
        return item
    if item.team_id and item.visibility == "team":
        authorize_team(db, actor, item.team_id, action)
    elif not actor.is_admin and item.owner_id != actor.id:
        raise HTTPException(404, "Template não encontrado")
    return item


def create_template(db, actor, payload):
    if payload.team_id:
        authorize_team(db, actor, payload.team_id, "write")
    values = payload.model_dump(exclude={"schema_version"})
    item = m.WriteupTemplate(owner_id=actor.id, visibility="team" if payload.team_id else "private", **values)
    db.add(item)
    db.flush()
    db.add(
        m.TemplateRevision(
            template_id=item.id,
            version=1,
            name=item.name,
            description=item.description,
            document=item.document,
            author_id=actor.id,
        )
    )
    audit(db, actor, "template.created", "template", item.id)
    db.commit()
    return fields(item)


def patch_template(db, actor, template_id, payload):
    item = template_resource(db, actor, template_id, "write")
    changes = payload.model_dump(exclude_unset=True)
    expected = changes.pop("expected_version")
    if any(value is None for value in changes.values()):
        raise HTTPException(422, "Campos do template não podem ser nulos")
    statement = (
        update(m.WriteupTemplate)
        .where(m.WriteupTemplate.id == item.id, m.WriteupTemplate.version == expected)
        .values(**changes, version=expected + 1)
        .execution_options(synchronize_session=False)
    )
    if db.execute(statement).rowcount != 1:
        db.rollback()
        raise HTTPException(409, "Template alterado por outra pessoa")
    db.expire(item)
    db.add(
        m.TemplateRevision(
            template_id=item.id,
            version=expected + 1,
            name=item.name,
            description=item.description,
            document=item.document,
            author_id=actor.id,
        )
    )
    audit(db, actor, "template.updated", "template", item.id, {"version": expected + 1})
    db.commit()
    return fields(item)


def notify(db, user_id, kind, title, entity_id, body=""):
    db.add(m.Notification(user_id=user_id, kind=kind, title=title, entity_id=entity_id, body=body))


def read_notification(db, actor, notification_id, read):
    item = db.get(m.Notification, notification_id)
    if not item or item.user_id != actor.id:
        raise HTTPException(404, "Notificação não encontrada")
    item.read_at = now() if read else None
    db.commit()
    return fields(item)


def update_admin_user(db, actor, user_id, payload):
    require_admin(actor)
    admins = db.scalars(
        select(m.User).where(m.User.is_admin.is_(True), m.User.is_active.is_(True)).with_for_update()
    ).all()
    item = db.get(m.User, user_id)
    if not item:
        raise HTTPException(404, "Usuário não encontrado")
    changes = payload.model_dump(exclude_unset=True)
    if any(value is None for value in changes.values()):
        raise HTTPException(422, "Valores administrativos não podem ser nulos")
    if (
        item.is_admin
        and item.is_active
        and (changes.get("is_admin") is False or changes.get("is_active") is False)
        and len(admins) <= 1
    ):
        raise HTTPException(409, "Mantenha pelo menos um administrador ativo")
    if changes.get("is_active") is False and item.is_active:
        managed_teams = db.scalars(
            select(m.TeamMember.team_id).where(m.TeamMember.user_id == item.id, m.TeamMember.role == "manager")
        ).all()
        for team_id in managed_teams:
            db.scalar(select(m.Team).where(m.Team.id == team_id).with_for_update())
            if manager_count(db, team_id) <= 1:
                raise HTTPException(409, "Transfira a gestão das equipes antes de desativar este usuário")
    for name, value in changes.items():
        setattr(item, name, value)
    if changes.get("is_active") is False:
        db.execute(
            update(m.SessionModel)
            .where(m.SessionModel.user_id == item.id, m.SessionModel.revoked_at.is_(None))
            .values(revoked_at=now())
        )
    audit(db, actor, "admin.user.updated", "user", item.id, changes)
    db.commit()
    return public_user(item)


def read_settings(db, actor):
    from app.config import settings

    require_admin(actor)
    values = {
        "registration_enabled": settings.registration_enabled,
        "retention_days": settings.retention_days,
        "backup_rpo_hours": 24,
        "backup_rto_hours": 8,
        "ai_enabled": settings.ai_enabled,
    }
    for item in db.scalars(select(m.ApplicationSetting)):
        values[item.key] = item.value.get("value")
    return values


def patch_settings(db, actor, payload):
    require_admin(actor)
    changes = payload.model_dump(exclude_unset=True)
    if any(value is None for value in changes.values()):
        raise HTTPException(422, "Configurações não podem ser nulas")
    for key, value in changes.items():
        item = db.get(m.ApplicationSetting, key)
        if item:
            item.value = {"value": value}
            item.updated_by = actor.id
        else:
            db.add(m.ApplicationSetting(key=key, value={"value": value}, updated_by=actor.id))
    audit(db, actor, "admin.settings.updated", "settings", "application", {"keys": list(changes)})
    db.commit()
    return read_settings(db, actor)


def create_comment(db, actor, writeup_id, payload):
    item = resource(db, actor, m.Writeup, writeup_id, "comment")
    if payload.section_id and payload.section_id not in {
        section["id"] for section in item.document.get("sections", [])
    }:
        raise HTTPException(422, "Seção não pertence ao writeup")
    comment = m.Comment(writeup_id=item.id, author_id=actor.id, **payload.model_dump())
    db.add(comment)
    db.flush()
    if item.owner_id != actor.id:
        notify(db, item.owner_id, "comment", "Novo comentário no writeup", item.id, payload.body[:500])
    audit(db, actor, "writeup.comment.created", "writeup", item.id)
    db.commit()
    return fields(comment)


def resolve_comment(db, actor, comment_id, resolved):
    comment = db.get(m.Comment, comment_id)
    if not comment:
        raise HTTPException(404, "Comentário não encontrado")
    item = resource(db, actor, m.Writeup, comment.writeup_id)
    # Comentários de equipe seguem o papel atual; ser autor não preserva
    # privilégios depois de um downgrade ou remoção da equipe.
    authorize(db, actor, item, "comment")
    comment.resolved_at = now() if resolved else None
    audit(db, actor, "writeup.comment.resolved", "writeup", item.id, {"comment_id": comment.id, "resolved": resolved})
    db.commit()
    return fields(comment)


def create_review(db, actor, writeup_id, payload):
    item = resource(db, actor, m.Writeup, writeup_id, "write")
    reviewer = db.get(m.User, payload.reviewer_id)
    if not reviewer or not reviewer.is_active:
        raise HTTPException(422, "Revisor inválido")
    if reviewer.id in {item.owner_id, actor.id}:
        raise HTTPException(422, "O revisor deve ser diferente do autor e do solicitante")
    revision_author = db.scalar(
        select(m.WriteupRevision.author_id).where(
            m.WriteupRevision.writeup_id == item.id, m.WriteupRevision.version == item.version
        )
    )
    if reviewer.id == revision_author:
        raise HTTPException(422, "O autor da versão não pode revisar sua própria edição")
    authorize(db, reviewer, item, "review")
    if db.scalar(
        select(m.ReviewRequest.id).where(
            m.ReviewRequest.writeup_id == item.id,
            m.ReviewRequest.reviewer_id == reviewer.id,
            m.ReviewRequest.version == item.version,
            m.ReviewRequest.status == "pending",
        )
    ):
        raise HTTPException(409, "Já existe revisão pendente para esta versão e revisor")
    review = m.ReviewRequest(
        writeup_id=item.id,
        requester_id=actor.id,
        reviewer_id=reviewer.id,
        version=item.version,
        comment=payload.comment,
    )
    db.add(review)
    db.flush()
    notify(db, reviewer.id, "review", "Writeup aguardando sua revisão", item.id, payload.comment)
    audit(db, actor, "writeup.review.requested", "writeup", item.id, {"review_id": review.id, "version": item.version})
    db.commit()
    return fields(review)


def decide_review(db, actor, review_id, payload):
    review = db.scalar(select(m.ReviewRequest).where(m.ReviewRequest.id == review_id).with_for_update())
    if not review:
        raise HTTPException(404, "Revisão não encontrada")
    item = resource(db, actor, m.Writeup, review.writeup_id, "review")
    if actor.id != review.reviewer_id or actor.id in {item.owner_id, review.requester_id}:
        raise HTTPException(403, "Somente o revisor designado pode decidir esta revisão")
    revision_author = db.scalar(
        select(m.WriteupRevision.author_id).where(
            m.WriteupRevision.writeup_id == item.id, m.WriteupRevision.version == review.version
        )
    )
    if actor.id == revision_author:
        raise HTTPException(403, "O autor da versão não pode aprovar sua própria edição")
    if review.status != "pending" or review.version != item.version:
        raise HTTPException(409, "A revisão expirou ou já foi decidida; solicite revisão da versão atual")
    result = db.execute(
        update(m.Writeup)
        .where(m.Writeup.id == item.id, m.Writeup.version == review.version, m.Writeup.deleted_at.is_(None))
        .values(
            status="approved" if payload.decision == "approved" else "changes_requested",
            approved_revision=review.version if payload.decision == "approved" else None,
        )
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "O writeup foi alterado durante a revisão")
    review.status = payload.decision
    review.comment = payload.comment
    review.decided_at = now()
    notify(db, item.owner_id, "review_decision", "Decisão de revisão recebida", item.id, payload.comment)
    audit(
        db,
        actor,
        "writeup.review.decided",
        "writeup",
        item.id,
        {"review_id": review.id, "decision": payload.decision, "version": review.version},
    )
    db.commit()
    return fields(review)


def dashboard(db, actor):
    def visible(model):
        statement = visible_query(select(model), model, actor, db)
        return statement.where(model.deleted_at.is_(None)) if hasattr(model, "deleted_at") else statement

    def count(statement):
        return db.scalar(select(func.count()).select_from(statement.subquery())) or 0

    competition_query = visible(m.Competition)
    competitions = db.scalars(competition_query.order_by(m.Competition.created_at.desc()).limit(100)).all()
    challenge_ids = visible(m.Challenge).with_only_columns(m.Challenge.id)
    category_counts = db.execute(
        select(m.Challenge.category, func.count())
        .where(m.Challenge.id.in_(challenge_ids))
        .group_by(m.Challenge.category)
    ).all()
    progress = {
        competition.id: {"competition_id": competition.id, "name": competition.name, "total": 0, "solved": 0}
        for competition in competitions
    }
    from sqlalchemy import case

    progress_counts = db.execute(
        select(m.Challenge.competition_id, func.count(), func.sum(case((m.Challenge.status == "solved", 1), else_=0)))
        .where(m.Challenge.id.in_(challenge_ids), m.Challenge.competition_id.in_(progress))
        .group_by(m.Challenge.competition_id)
    ).all()
    for competition_id, total, solved in progress_counts:
        progress[competition_id]["total"] = total
        progress[competition_id]["solved"] = solved
    for item in progress.values():
        item["percent"] = round(100 * item["solved"] / item["total"], 1) if item["total"] else 0
    # Apenas ações sobre recursos efetivamente visíveis; IDs de recursos privados não vazam.
    visible_ids = []
    for model in (m.Competition, m.Challenge, m.Writeup, m.Evidence):
        visible_ids.append(m.AuditLog.entity_id.in_(visible(model).with_only_columns(model.id)))
    activity_query = (
        select(m.AuditLog)
        .where(
            or_(*visible_ids, and_(m.AuditLog.actor_id == actor.id, m.AuditLog.entity_type.in_(["team", "template"])))
        )
        .order_by(m.AuditLog.created_at.desc())
        .limit(15)
    )
    writeups = visible(m.Writeup)
    return {
        "competitions": count(competition_query),
        "challenges": count(visible(m.Challenge)),
        "writeups": count(writeups),
        "evidences": count(visible(m.Evidence)),
        "completed_writeups": count(writeups.where(m.Writeup.status.in_(["approved", "published", "completed"]))),
        "in_progress_writeups": count(
            writeups.where(m.Writeup.status.in_(["draft", "in_progress", "changes_requested", "review"]))
        ),
        "recent_activity": [fields(row) for row in db.scalars(activity_query)],
        "category_stats": [{"category": key, "count": value} for key, value in sorted(category_counts)],
        "competition_progress": list(progress.values()),
        # Snapshots publicados são recursos separados e nunca entram no
        # dashboard agregado, evitando reexpor conteúdo após revogação.
        "publication_history": [],
    }


def search(
    db,
    actor,
    *,
    q="",
    category=None,
    tags=None,
    author_id=None,
    tool=None,
    language=None,
    date_from=None,
    date_to=None,
    sort="recent",
    page=1,
    page_size=25,
):
    """Pesquisa dos quatro tipos com ACL antes de qualquer filtro ou paginação."""
    tag_list = [tag.strip() for tag in (tags or "").split(",") if tag.strip()]
    postgres = db.bind.dialect.name == "postgresql"
    model_kinds = [
        (m.Competition, "competition"),
        (m.Challenge, "challenge"),
        (m.Writeup, "writeup"),
        (m.Evidence, "evidence"),
    ]
    projections = []
    for model, kind in model_kinds:
        query = visible_query(select(model), model, actor, db).where(model.deleted_at.is_(None))
        title_column = model.title if model is m.Writeup else model.name
        text_parts = [func.coalesce(title_column, "")]
        if hasattr(model, "description"):
            text_parts.append(func.coalesce(model.description, ""))
        if model is m.Writeup:
            text_parts.append(func.coalesce(cast(model.document, String), ""))
        if hasattr(model, "notes"):
            text_parts.append(func.coalesce(model.notes, ""))
        searchable = text_parts[0]
        for part in text_parts[1:]:
            searchable = searchable + " " + part
        if q:
            if postgres:
                query = query.where(
                    func.to_tsvector(literal_column("'simple'"), searchable).op("@@")(
                        func.websearch_to_tsquery(literal_column("'simple'"), q)
                    )
                )
            else:
                query = query.where(searchable.ilike(f"%{q}%"))
        if author_id:
            query = query.where(model.owner_id == author_id)
        if date_from:
            query = query.where(model.created_at >= date_from)
        if date_to:
            query = query.where(model.created_at <= date_to)
        if category:
            visible_category_challenges = visible_query(select(m.Challenge), m.Challenge, actor, db).where(
                m.Challenge.category == category
            )
            if model is m.Challenge:
                query = query.where(model.category == category)
            elif model in (m.Writeup, m.Evidence):
                query = query.where(
                    model.challenge_id.in_(visible_category_challenges.with_only_columns(m.Challenge.id))
                )
            else:
                query = query.where(
                    model.id.in_(visible_category_challenges.with_only_columns(m.Challenge.competition_id))
                )
        if tag_list:
            if hasattr(model, "tags"):
                for tag in tag_list:
                    # JSON array membership uses PostgreSQL jsonb containment in production.
                    if postgres:
                        from sqlalchemy.dialects.postgresql import JSONB

                        query = query.where(cast(model.tags, JSONB).contains([tag]))
                    else:
                        query = query.where(cast(model.tags, String).like(f'%"{tag}"%'))
            elif model is m.Writeup:
                tag_query = select(m.Challenge.id)
                for tag in tag_list:
                    if postgres:
                        from sqlalchemy.dialects.postgresql import JSONB

                        tag_query = tag_query.where(cast(m.Challenge.tags, JSONB).contains([tag]))
                    else:
                        tag_query = tag_query.where(cast(m.Challenge.tags, String).like(f'%"{tag}"%'))
                query = query.where(model.challenge_id.in_(tag_query))
            else:
                continue
        if tool or language:
            if model is m.Writeup:
                content = cast(model.document, String)
                if tool:
                    query = query.where(or_(content.ilike(f"%{tool}%"), cast(model.tools, String).ilike(f"%{tool}%")))
                if language:
                    query = query.where(
                        or_(content.ilike(f"%```{language}%"), cast(model.languages, String).ilike(f"%{language}%"))
                    )
            elif model is m.Evidence:
                content = cast(model.metadata_json, String)
                if tool:
                    query = query.where(content.ilike(f"%{tool}%"))
                if language:
                    query = query.where(content.ilike(f"%{language}%"))
            else:
                continue
        projections.append(
            query.with_only_columns(
                model.id.label("id"),
                literal(kind).label("type"),
                title_column.label("title"),
                model.created_at.label("created_at"),
            )
        )
    if not projections:
        return {"items": [], "total": 0, "page": page, "page_size": page_size}
    # Paginação global no banco; a memória permanece limitada a uma página mesmo em páginas distantes.
    combined = union_all(*projections).subquery()
    total = db.scalar(select(func.count()).select_from(combined)) or 0
    ordering = (
        func.lower(combined.c.title).asc()
        if sort == "name"
        else combined.c.created_at.asc()
        if sort == "oldest"
        else combined.c.created_at.desc()
    )
    page_rows = db.execute(
        select(combined).order_by(ordering, combined.c.id).offset((page - 1) * page_size).limit(page_size)
    ).all()
    by_key = {}
    for model, kind in model_kinds:
        ids = [row.id for row in page_rows if row.type == kind]
        if ids:
            for resource_row in db.scalars(visible_query(select(model).where(model.id.in_(ids)), model, actor, db)):
                by_key[(kind, resource_row.id)] = resource_row
    result_rows = []
    for projection in page_rows:
        row = by_key.get((projection.type, projection.id))
        if row is not None:
            result_rows.append(
                {
                    "type": projection.type,
                    "id": row.id,
                    "title": projection.title,
                    "owner_id": row.owner_id,
                    "created_at": row.created_at,
                    "category": getattr(row, "category", None),
                    "tags": getattr(row, "tags", []),
                    "excerpt": getattr(row, "description", "")[:300],
                    "resource": fields(row),
                }
            )
    return {
        "items": result_rows,
        "total": total,
        "page": page,
        "page_size": page_size,
    }
