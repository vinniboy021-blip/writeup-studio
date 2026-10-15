from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select, update

from app.config import settings
from app.db import utcnow
from app.models import SessionModel, User
from app.modules.identity import services
from app.modules.identity.schemas import LoginIn, PasswordIn, RegisterIn
from app.schemas import UserOut
from app.security import (
    DB,
    audit,
    check_request_origin,
    get_actor,
    password_hash,
    rate_limit,
    require_csrf,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["Autenticação"])
Actor = Annotated[User, Depends(get_actor)]
Writer = Annotated[User, Depends(require_csrf)]


def login_limit(request: Request, email: str):
    # Client IP is the transport peer; untrusted forwarded headers are ignored.
    ip = request.client.host if request.client else "unknown"
    rate_limit("auth:ip:" + ip, settings.login_rate_limit * 10, settings.login_rate_window_seconds)
    rate_limit("auth:account:" + email.lower(), settings.login_rate_limit, settings.login_rate_window_seconds)
    check_request_origin(request)


@router.post("/register", status_code=201)
def register(data: RegisterIn, request: Request, response: Response, db: DB):
    login_limit(request, str(data.email))
    return services.register(db, data, request, response)


@router.post("/login")
def login(data: LoginIn, request: Request, response: Response, db: DB):
    login_limit(request, str(data.email))
    return services.login(db, data, request, response)


@router.get("/me")
def me(request: Request, response: Response, actor: Actor):
    response.headers["Cache-Control"] = "no-store"
    return {"user": UserOut.model_validate(actor).model_dump(), "csrf_token": request.state.session.csrf_token}


@router.post("/logout")
def logout(request: Request, response: Response, actor: Writer, db: DB):
    request.state.session.revoked_at = utcnow()
    audit(db, actor, "session.revoked", "session", request.state.session.id)
    db.commit()
    response.delete_cookie("ctf_session", path="/", httponly=True, secure=settings.cookie_secure, samesite="lax")
    return {"ok": True}


@router.get("/sessions")
def sessions(request: Request, actor: Actor, db: DB):
    rows = db.scalars(
        select(SessionModel)
        .where(SessionModel.user_id == actor.id, SessionModel.revoked_at.is_(None), SessionModel.expires_at > utcnow())
        .order_by(SessionModel.created_at.desc())
        .limit(100)
    ).all()
    items = [
        {
            "id": row.id,
            "created_at": row.created_at,
            "expires_at": row.expires_at,
            "user_agent": row.user_agent,
            "current": row.id == request.state.session.id,
        }
        for row in rows
    ]
    return {"items": items, "total": len(items), "page": 1, "page_size": 100}


@router.delete("/sessions/{session_id}")
def revoke_session(session_id: str, request: Request, response: Response, actor: Writer, db: DB):
    session = db.get(SessionModel, session_id)
    if session is None or session.user_id != actor.id:
        raise HTTPException(404, "Sessão não encontrada")
    session.revoked_at = utcnow()
    audit(db, actor, "session.revoked", "session", session.id)
    db.commit()
    if session.id == request.state.session.id:
        response.delete_cookie("ctf_session", path="/", httponly=True, secure=settings.cookie_secure, samesite="lax")
    return {"ok": True}


@router.post("/password")
def change_password(data: PasswordIn, request: Request, actor: Writer, db: DB):
    rate_limit("password:" + actor.id, 5, 60)
    if not verify_password(data.current_password, actor.password_hash):
        raise HTTPException(403, "Senha atual inválida")
    actor.password_hash = password_hash.hash(data.new_password)
    db.execute(
        update(SessionModel)
        .where(SessionModel.user_id == actor.id, SessionModel.id != request.state.session.id)
        .values(revoked_at=utcnow())
    )
    request.state.session.csrf_token = __import__("secrets").token_urlsafe(32)
    audit(db, actor, "user.password_changed", "user", actor.id)
    db.commit()
    return {"ok": True, "csrf_token": request.state.session.csrf_token}
