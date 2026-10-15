import secrets
from datetime import timedelta

from fastapi import HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.db import utcnow
from app.models import ApplicationSetting, SessionModel, User
from app.schemas import UserOut
from app.security import audit, digest, password_hash, verify_password


def session_response(db: Session, user: User, response: Response, request: Request):
    raw = secrets.token_urlsafe(48)
    session = SessionModel(
        user_id=user.id,
        token_hash=digest(raw),
        csrf_token=secrets.token_urlsafe(32),
        expires_at=utcnow() + timedelta(hours=settings.session_ttl_hours),
        user_agent=request.headers.get("user-agent", "")[:500],
    )
    db.add(session)
    audit(db, user, "session.created", "user", user.id)
    db.commit()
    response.set_cookie(
        "ctf_session",
        raw,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=settings.session_ttl_hours * 3600,
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"
    return {"user": UserOut.model_validate(user).model_dump(), "csrf_token": session.csrf_token}


def register(db: Session, data, request: Request, response: Response):
    option = db.get(ApplicationSetting, "registration_enabled")
    enabled = option.value.get("value", settings.registration_enabled) if option else settings.registration_enabled
    if not enabled:
        raise HTTPException(403, "Cadastro público desabilitado")
    email = str(data.email).lower()
    if db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(409, "Email já cadastrado")
    user = User(
        email=email, name=data.name, password_hash=password_hash.hash(data.password), is_admin=False, is_active=True
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Email já cadastrado") from exc
    audit(db, user, "user.registered", "user", user.id)
    return session_response(db, user, response, request)


def login(db: Session, data, request: Request, response: Response):
    user = db.scalar(select(User).where(User.email == str(data.email).lower()))
    valid = verify_password(data.password, user.password_hash if user else None)
    if not valid or not user or not user.is_active:
        raise HTTPException(401, "Credenciais inválidas")
    return session_response(db, user, response, request)
