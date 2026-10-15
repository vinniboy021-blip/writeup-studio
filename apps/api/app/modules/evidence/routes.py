# SPDX-License-Identifier: MIT
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import Text, cast, func, or_, select, update
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import Evidence, EvidenceAnnotation, EvidenceEvent, EvidenceVersion, User, Writeup, WriteupEvidence
from app.security import audit, authorize, get_actor, require_csrf, visible_query

from .schemas import AnnotationCreate, EvidencePatch
from .service import (annotate, annotation_out, conflict, create_evidence, event, evidence_out,
                      get_evidence, update_metadata, utcnow, version_out)
from .storage import object_response

router = APIRouter(tags=["Evidências"])
DB = Annotated[Session, Depends(get_db)]
Actor = Annotated[User, Depends(get_actor)]
Writer = Annotated[User, Depends(require_csrf)]


def _page(db: Session, statement, page: int, page_size: int, transform=lambda row: row):
    total = db.scalar(select(func.count()).select_from(statement.order_by(None).subquery())) or 0
    rows = db.scalars(statement.offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": [transform(row) for row in rows], "total": total, "page": page, "page_size": page_size}


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@router.get("/evidences")
def list_evidences(db: DB, actor: Actor, page: int = Query(1, ge=1), page_size: int = Query(24, ge=1, le=100),
                   q: str = Query("", max_length=300), tag: str | None = Query(None, max_length=80),
                   challenge_id: str | None = None, team_id: str | None = None, mime_type: str | None = None,
                   sort: Literal["newest", "oldest", "name", "manual"] = "newest"):
    stmt = visible_query(select(Evidence), Evidence, actor, db).where(Evidence.deleted_at.is_(None))
    if q:
        pattern = f"%{_escape_like(q)}%"
        stmt = stmt.where(or_(Evidence.name.ilike(pattern, escape="\\"), Evidence.description.ilike(pattern, escape="\\"),
                             Evidence.origin.ilike(pattern, escape="\\")))
    if tag:
        stmt = stmt.where(cast(Evidence.tags, Text).like(f'%"{_escape_like(tag)}"%', escape="\\"))
    if challenge_id:
        stmt = stmt.where(Evidence.challenge_id == challenge_id)
    if team_id:
        stmt = stmt.where(Evidence.team_id == team_id)
    if mime_type:
        stmt = stmt.where(Evidence.mime_type == mime_type)
    orders = {"newest": Evidence.received_at.desc(), "oldest": Evidence.received_at.asc(),
              "name": Evidence.name.asc(), "manual": Evidence.metadata_json["manual_order"].as_integer().asc()}
    return _page(db, stmt.order_by(orders[sort], Evidence.id), page, page_size, evidence_out)


@router.post("/evidences", status_code=201)
def upload_evidence(db: DB, actor: Writer, file: UploadFile = File(...),
                    name: str | None = Form(None, max_length=240), description: str = Form("", max_length=10000),
                    origin: str = Form("", max_length=1000), team_id: str | None = Form(None),
                    challenge_id: str | None = Form(None), captured_at: datetime | None = Form(None),
                    tags: str = Form("[]", max_length=4096), visibility: Literal["private", "team"] = Form("private")):
    try:
        parsed_tags = json.loads(tags)
        if not isinstance(parsed_tags, list) or any(not isinstance(tag, str) for tag in parsed_tags):
            raise ValueError("Tags devem ser array de strings")
        if len(parsed_tags) > 30:
            raise ValueError("Máximo de 30 tags")
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(422, "Tags devem ser um array JSON com até 30 strings") from exc
    evidence = create_evidence(db, actor, file.file, file.filename or "", file.content_type,
                               name=name, description=description, origin=origin, team_id=team_id,
                               challenge_id=challenge_id, captured_at=captured_at, tags=parsed_tags, visibility=visibility)
    return evidence_out(evidence)


@router.get("/evidences/{evidence_id}")
def evidence_detail(evidence_id: str, db: DB, actor: Actor):
    return evidence_out(get_evidence(db, actor, evidence_id))


@router.patch("/evidences/{evidence_id}")
def evidence_patch(evidence_id: str, data: EvidencePatch, db: DB, actor: Writer):
    evidence = get_evidence(db, actor, evidence_id, "edit")
    return evidence_out(update_metadata(db, actor, evidence, data))


@router.delete("/evidences/{evidence_id}")
def delete_evidence(evidence_id: str, db: DB, actor: Writer, expected_version: int | None = Query(None, ge=1)):
    evidence = get_evidence(db, actor, evidence_id, "delete")
    if db.scalar(select(WriteupEvidence.id).where(WriteupEvidence.evidence_id == evidence.id).limit(1)):
        raise HTTPException(409, "Desassocie a evidência dos writeups antes de excluí-la")
    version = expected_version or evidence.version
    result = db.execute(update(Evidence).where(Evidence.id == evidence.id, Evidence.version == version,
                                               Evidence.deleted_at.is_(None))
                        .values(deleted_at=utcnow(), updated_at=utcnow(), version=version + 1)
                        .execution_options(synchronize_session=False))
    if result.rowcount != 1:
        conflict(db, evidence.id)
    event(db, actor, evidence, "deleted", {"retention_days": settings.retention_days})
    audit(db, actor, "evidence.delete", "evidence", evidence.id)
    db.commit()
    return {"ok": True, "retention_days": settings.retention_days}


class TicketInput(BaseModel):
    version_id: str | None = Field(default=None, max_length=36)


def _signature(encoded: str) -> str:
    return hmac.new(settings.secret_key.encode(), encoded.encode(), hashlib.sha256).hexdigest()


def _verify_ticket(ticket: str | None, actor: User, evidence_id: str, version_id: str | None = None):
    if ticket is None:
        return
    try:
        encoded, signature = ticket.split(".", 1)
        if not hmac.compare_digest(signature, _signature(encoded)):
            raise ValueError("Assinatura inválida")
        payload = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
        if payload["sub"] != actor.id or payload["eid"] != evidence_id or payload["vid"] != version_id or payload["exp"] < time.time():
            raise ValueError("Ticket expirado ou escopo incorreto")
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(403, "Ticket inválido ou expirado") from exc


@router.post("/evidences/{evidence_id}/download-ticket")
def download_ticket(evidence_id: str, data: TicketInput, db: DB, actor: Writer):
    evidence = get_evidence(db, actor, evidence_id)
    if data.version_id:
        version = db.get(EvidenceVersion, data.version_id)
        if not version or version.evidence_id != evidence.id:
            raise HTTPException(404, "Versão não encontrada")
    expires = int(time.time()) + settings.s3_signed_url_seconds
    payload = {"sub": actor.id, "eid": evidence.id, "vid": data.version_id, "exp": expires}
    encoded = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    ticket = f"{encoded}.{_signature(encoded)}"
    path = f"/api/v1/evidences/{evidence.id}"
    path += f"/versions/{data.version_id}/download" if data.version_id else "/download"
    return {"url": f"{path}?ticket={ticket}", "expires_at": expires,
            "authentication_required": True}


@router.get("/evidences/{evidence_id}/download")
def download_original(evidence_id: str, db: DB, actor: Actor, ticket: str | None = Query(None, max_length=2048)):
    evidence = get_evidence(db, actor, evidence_id)
    _verify_ticket(ticket, actor, evidence.id)
    audit(db, actor, "evidence.download", "evidence", evidence.id, {"kind": "original"})
    db.commit()
    return object_response(evidence.storage_key, evidence.mime_type, evidence.name)


@router.get("/evidences/{evidence_id}/thumbnail")
def download_thumbnail(evidence_id: str, db: DB, actor: Actor):
    evidence = get_evidence(db, actor, evidence_id)
    if not evidence.mime_type.startswith("image/"):
        raise HTTPException(422, "Evidência sem miniatura visual")
    version = db.scalar(select(EvidenceVersion).where(EvidenceVersion.evidence_id == evidence.id,
                                                      EvidenceVersion.kind == "thumbnail")
                        .order_by(EvidenceVersion.version.desc()).limit(1))
    if not version:
        # A worker may still be processing. Avoid leaking originals or returning a broken image.
        from .jobs import generate_thumbnail
        generate_thumbnail(evidence.id)
        db.expire_all()
        version = db.scalar(select(EvidenceVersion).where(EvidenceVersion.evidence_id == evidence.id,
                                                          EvidenceVersion.kind == "thumbnail")
                            .order_by(EvidenceVersion.version.desc()).limit(1))
    if not version:
        raise HTTPException(503, "Miniatura indisponível")
    return object_response(version.storage_key, "image/png", "thumbnail.png", inline=True)


@router.get("/evidences/{evidence_id}/versions")
def list_versions(evidence_id: str, db: DB, actor: Actor, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100)):
    evidence = get_evidence(db, actor, evidence_id)
    return _page(db, select(EvidenceVersion).where(EvidenceVersion.evidence_id == evidence.id)
                 .order_by(EvidenceVersion.version.desc(), EvidenceVersion.created_at.desc()), page, page_size, version_out)


@router.get("/evidences/{evidence_id}/versions/{version_id}/download")
def download_version(evidence_id: str, version_id: str, db: DB, actor: Actor,
                     ticket: str | None = Query(None, max_length=2048)):
    evidence = get_evidence(db, actor, evidence_id)
    _verify_ticket(ticket, actor, evidence.id, version_id)
    version = db.get(EvidenceVersion, version_id)
    if not version or version.evidence_id != evidence.id:
        raise HTTPException(404, "Versão não encontrada")
    audit(db, actor, "evidence.download", "evidence", evidence.id, {"kind": version.kind, "version": version.version})
    db.commit()
    name = evidence.name if version.kind == "original" else f"{evidence.name.rsplit('.', 1)[0]}-v{version.version}.png"
    return object_response(version.storage_key, version.mime_type, name, inline=version.kind != "original")


@router.get("/evidences/{evidence_id}/annotations")
def list_annotations(evidence_id: str, db: DB, actor: Actor,
                     page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100)):
    evidence = get_evidence(db, actor, evidence_id)
    return _page(db, select(EvidenceAnnotation).where(EvidenceAnnotation.evidence_id == evidence.id)
                 .order_by(EvidenceAnnotation.version.desc()), page, page_size, annotation_out)


@router.post("/evidences/{evidence_id}/annotations", status_code=201)
def create_annotation(evidence_id: str, data: AnnotationCreate, db: DB, actor: Writer):
    return annotate(db, actor, get_evidence(db, actor, evidence_id, "edit"), data)


def _event_out(row: EvidenceEvent):
    return {field: getattr(row, field) for field in ("id", "evidence_id", "actor_id", "event_type", "details", "created_at")}


@router.get("/timeline")
def timeline(db: DB, actor: Actor, evidence_id: str | None = None, writeup_id: str | None = None,
             page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100)):
    allowed_ids = visible_query(select(Evidence.id), Evidence, actor, db).where(Evidence.deleted_at.is_(None))
    stmt = select(EvidenceEvent).where(EvidenceEvent.evidence_id.in_(allowed_ids))
    if evidence_id:
        get_evidence(db, actor, evidence_id)
        stmt = stmt.where(EvidenceEvent.evidence_id == evidence_id)
    if writeup_id:
        writeup = db.get(Writeup, writeup_id)
        if not writeup or writeup.deleted_at is not None:
            raise HTTPException(404, "Writeup não encontrado")
        authorize(db, actor, writeup)
        stmt = stmt.where(EvidenceEvent.evidence_id.in_(select(WriteupEvidence.evidence_id)
                                                       .where(WriteupEvidence.writeup_id == writeup_id)))
    return _page(db, stmt.order_by(EvidenceEvent.created_at.desc(), EvidenceEvent.id), page, page_size, _event_out)


@router.get("/evidences/{evidence_id}/timeline")
def evidence_timeline(evidence_id: str, db: DB, actor: Actor, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100)):
    return timeline(db, actor, evidence_id=evidence_id, page=page, page_size=page_size)
