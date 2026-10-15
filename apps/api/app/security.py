"""Session authentication, CSRF, scoped RBAC and auditable actions."""

from __future__ import annotations

import hashlib
import secrets
import threading
import time
from collections import OrderedDict, deque
from contextvars import ContextVar
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from pwdlib import PasswordHash
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db, utcnow
from app.models import AuditLog, SessionModel, Team, TeamMember, User, WriteupTemplate


DB = Annotated[Session, Depends(get_db)]
password_hash = PasswordHash.recommended()  # Argon2id only; startup fails when unavailable.
correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)
_dummy_hash = password_hash.hash(secrets.token_urlsafe(32))
_rate_lock = threading.Lock()
_attempts: OrderedDict[str, deque[float]] = OrderedDict()


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def verify_password(value: str, encoded: str | None) -> bool:
    candidate = encoded if encoded and encoded.startswith("$argon2id$") else _dummy_hash
    try:
        valid = password_hash.verify(value, candidate)
    except Exception:
        return False
    return bool(encoded and encoded.startswith("$argon2id$") and valid)


def rate_limit(key: str, limit: int, window: int) -> None:
    """Atomic Redis fixed window; bounded sliding windows for local development."""
    safe_key = "ctf:rate:" + digest(key)
    if settings.rate_limit_backend == "redis":
        import redis

        try:
            client = redis.Redis.from_url(settings.redis_url, socket_timeout=2, socket_connect_timeout=2)
            count = client.eval(
                "local n=redis.call('INCR',KEYS[1]); if n==1 then redis.call('EXPIRE',KEYS[1],ARGV[1]) end; return n",
                1,
                safe_key,
                window,
            )
        except redis.RedisError as exc:
            raise HTTPException(503, "Proteção de autenticação temporariamente indisponível") from exc
        if count > limit:
            raise HTTPException(429, "Limite de tentativas excedido", headers={"Retry-After": str(window)})
        return
    now = time.monotonic()
    with _rate_lock:
        values = _attempts.setdefault(safe_key, deque())
        _attempts.move_to_end(safe_key)
        while values and now - values[0] >= window:
            values.popleft()
        if len(values) >= limit:
            raise HTTPException(429, "Limite de tentativas excedido", headers={"Retry-After": str(window)})
        values.append(now)
        while len(_attempts) > 10000:
            _attempts.popitem(last=False)


def check_request_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if origin and origin.rstrip("/") not in settings.allowed_origins:
        raise HTTPException(403, "Origem não autorizada")
    if request.headers.get("sec-fetch-site") == "cross-site" and not origin:
        raise HTTPException(403, "Origem não autorizada")


def get_actor(request: Request, db: DB) -> User:
    token = request.cookies.get("ctf_session", "")
    if not token or len(token) > 200:
        raise HTTPException(401, "Autenticação necessária")
    session = db.scalar(
        select(SessionModel).where(
            SessionModel.token_hash == digest(token),
            SessionModel.revoked_at.is_(None),
            SessionModel.expires_at > utcnow(),
        )
    )
    if session is None:
        raise HTTPException(401, "Sessão inválida ou expirada")
    actor = db.get(User, session.user_id)
    if actor is None or not actor.is_active:
        raise HTTPException(401, "Usuário indisponível")
    request.state.session = session
    request.state.actor_id = actor.id
    return actor


def require_csrf(request: Request, actor: Annotated[User, Depends(get_actor)]) -> User:
    check_request_origin(request)
    token = request.headers.get("X-CSRF-Token", "")
    session = request.state.session
    if not token or not secrets.compare_digest(token, session.csrf_token):
        raise HTTPException(403, "Token CSRF inválido")
    return actor


_TEAM_ACTIONS = {
    "read": {"manager", "editor", "reviewer", "viewer"},
    "write": {"manager", "editor"},
    "edit": {"manager", "editor"},
    "create": {"manager", "editor"},
    "delete": {"manager", "editor"},
    "comment": {"manager", "editor", "reviewer"},
    "review": {"manager", "reviewer"},
    "approve": {"manager", "reviewer"},
    "publish": {"manager", "editor"},
    "export": {"manager", "editor", "reviewer", "viewer"},
    "manage": {"manager"},
    "invite": {"manager"},
}


def authorize_team(db: Session, actor: User, team_id: str, action: str = "read") -> Team:
    team = db.get(Team, team_id)
    if team is None:
        raise HTTPException(404, "Equipe não encontrada")
    if actor.is_admin:
        return team
    role = db.scalar(select(TeamMember.role).where(TeamMember.team_id == team_id, TeamMember.user_id == actor.id))
    if role not in _TEAM_ACTIONS.get(action, set()):
        raise HTTPException(403, "Permissão insuficiente na equipe")
    return team


def authorize(db: Session, actor: User, resource, action: str = "read"):
    if resource is None or getattr(resource, "deleted_at", None) is not None:
        raise HTTPException(404, "Recurso não encontrado")
    if actor.is_admin:
        return resource
    if isinstance(resource, WriteupTemplate) and resource.owner_id is None and resource.team_id is None:
        if action in {"read", "export"}:
            return resource
        raise HTTPException(403, "Templates globais são administrados pela operação")
    if getattr(resource, "visibility", "private") == "team":
        team_id = getattr(resource, "team_id", None)
        if not team_id:
            raise HTTPException(404, "Recurso não encontrado")
        authorize_team(db, actor, team_id, action)
        return resource
    if getattr(resource, "owner_id", None) != actor.id:
        raise HTTPException(404, "Recurso não encontrado")
    if action in {"review", "approve"}:
        raise HTTPException(403, "O autor não pode aprovar seu próprio documento")
    return resource


def visible_query(statement, model, actor: User, db: Session):
    if hasattr(model, "deleted_at"):
        statement = statement.where(model.deleted_at.is_(None))
    if actor.is_admin:
        return statement
    teams = select(TeamMember.team_id).where(TeamMember.user_id == actor.id)
    conditions = [model.owner_id == actor.id]
    if hasattr(model, "visibility") and hasattr(model, "team_id"):
        # Owner access does not bypass current team membership for team resources.
        conditions = [
            ((model.owner_id == actor.id) & (model.visibility != "team")),
            ((model.visibility == "team") & model.team_id.in_(teams)),
        ]
    elif hasattr(model, "team_id"):
        conditions.append(model.team_id.in_(teams))
    if model is WriteupTemplate:
        conditions.append(model.owner_id.is_(None) & model.team_id.is_(None))
    return statement.where(or_(*conditions))


def audit(db: Session, actor: User | None, action: str, entity_type: str, entity_id: str, details: dict | None = None):
    entry = AuditLog(
        actor_id=actor.id if actor else None,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        details=details or {},
        correlation_id=correlation_id.get(),
    )
    db.add(entry)
    return entry


# Compatibility names for early releases.
actor = get_actor
csrf = require_csrf
ph = password_hash
