# SPDX-License-Identifier: MIT
from __future__ import annotations

import hashlib
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (Challenge, Evidence, EvidenceAnnotation, EvidenceEvent, EvidenceVersion,
                        ReviewRequest, User, Writeup, WriteupEvidence)
from app.security import audit, authorize, authorize_team

from .rendering import render_annotation, thumbnail
from .schemas import AnnotationCreate, EvidencePatch
from .storage import delete_object, put_object, read_object
from .validation import validate_file


def utcnow():
    return datetime.now(timezone.utc)


def evidence_out(evidence: Evidence) -> dict:
    fields = ("id", "owner_id", "team_id", "challenge_id", "name", "description", "origin", "captured_at",
              "received_at", "sha256", "size", "mime_type", "extension", "version", "tags", "visibility",
              "created_at", "updated_at")
    result = {field: getattr(evidence, field) for field in fields}
    result["metadata"] = evidence.metadata_json
    return result


def version_out(version: EvidenceVersion) -> dict:
    return {field: getattr(version, field) for field in ("id", "evidence_id", "version", "sha256", "size",
                                                       "mime_type", "author_id", "kind", "created_at")}


def annotation_out(annotation: EvidenceAnnotation) -> dict:
    return {field: getattr(annotation, field) for field in ("id", "evidence_id", "author_id", "version", "data", "created_at")}


def get_evidence(db: Session, actor: User, evidence_id: str, action: str = "read") -> Evidence:
    evidence = db.get(Evidence, evidence_id)
    if not evidence or evidence.deleted_at is not None:
        raise HTTPException(404, "Evidência não encontrada")
    authorize(db, actor, evidence, action)
    return evidence


def event(db: Session, actor: User, evidence: Evidence, kind: str, details: dict | None = None):
    db.add(EvidenceEvent(evidence_id=evidence.id, actor_id=actor.id, event_type=kind, details=details or {}))


def _relation(db: Session, actor: User, team_id: str | None, challenge_id: str | None, visibility: str):
    if visibility == "team" and not team_id:
        raise HTTPException(422, "Visibilidade de equipe exige uma equipe")
    if team_id:
        authorize_team(db, actor, team_id, "edit")
    if challenge_id:
        challenge = db.get(Challenge, challenge_id)
        if not challenge or challenge.deleted_at is not None:
            raise HTTPException(404, "Desafio não encontrado")
        authorize(db, actor, challenge, "edit")
        if challenge.team_id != team_id:
            raise HTTPException(422, "Evidência e desafio devem pertencer ao mesmo workspace")
        if not challenge.team_id and challenge.owner_id != actor.id and not actor.is_admin:
            raise HTTPException(403, "Desafio privado pertence a outro usuário")


def _clean_name(name: str) -> str:
    name = Path(name.replace("\\", "/")).name
    if not name or len(name) > 240 or any(ord(c) < 32 for c in name):
        raise HTTPException(422, "Nome de arquivo inválido")
    return name


def create_evidence(db: Session, actor: User, source: BinaryIO, filename: str, declared_mime: str | None,
                    *, name: str | None = None, description: str = "", origin: str = "",
                    team_id: str | None = None, challenge_id: str | None = None,
                    captured_at: datetime | None = None, tags: list[str] | None = None,
                    visibility: str = "private", metadata: dict | None = None) -> Evidence:
    """Aceita stream; utilizado também por Kali para guardar stdout autêntico."""
    _relation(db, actor, team_id, challenge_id, visibility)
    filename = _clean_name(filename)
    display_name = _clean_name(name or filename)
    if len(description) > 10000 or len(origin) > 1000:
        raise HTTPException(422, "Descrição ou origem acima do limite")
    if captured_at is not None:
        if captured_at.tzinfo is None:
            raise HTTPException(422, "Horário de captura deve incluir fuso horário")
        captured_at = captured_at.astimezone(timezone.utc)
    if visibility not in {"private", "team"}:
        raise HTTPException(422, "Evidências não podem ser publicadas pelo upload")
    tags = EvidencePatch.clean_tags(tags or [])
    EvidencePatch.bounded_metadata(metadata)
    keys: list[str] = []
    size = 0
    sha = hashlib.sha256()
    with tempfile.SpooledTemporaryFile(max_size=1024 * 1024, mode="w+b") as spool:
        source.seek(0)
        while chunk := source.read(65536):
            size += len(chunk)
            if size > settings.max_upload_bytes:
                raise HTTPException(413, "Arquivo acima do limite permitido")
            sha.update(chunk)
            spool.write(chunk)
        spool.seek(0)
        mime, extension, detected_metadata = validate_file(spool, filename, declared_mime)
        evidence_id = str(uuid.uuid4())
        original_key = f"evidences/{evidence_id}/original/{uuid.uuid4().hex}{extension}"
        now = utcnow()
        evidence = Evidence(id=evidence_id, owner_id=actor.id, team_id=team_id, challenge_id=challenge_id,
                            name=display_name, description=description, origin=origin, captured_at=captured_at,
                            received_at=now, sha256=sha.hexdigest(), size=size, mime_type=mime, extension=extension,
                            storage_key=original_key, version=1, tags=tags, metadata_json={**(metadata or {}), **detected_metadata},
                            visibility=visibility, created_at=now, updated_at=now)
        try:
            put_object(original_key, spool, mime)
            keys.append(original_key)
            db.add(evidence)
            db.flush()
            db.add(EvidenceVersion(evidence_id=evidence.id, version=1, storage_key=original_key,
                                   sha256=evidence.sha256, size=size, mime_type=mime, author_id=actor.id, kind="original"))
            event(db, actor, evidence, "upload", {"sha256": evidence.sha256, "size": size,
                                                  "captured_at_declared": captured_at.isoformat() if captured_at else None,
                                                  "received_at_server": now.isoformat()})
            audit(db, actor, "evidence.upload", "evidence", evidence.id, {"sha256": evidence.sha256, "size": size})
            if mime.startswith("image/") and not getattr(settings, "queue_enabled", False):
                spool.seek(0)
                preview = thumbnail(spool.read())
                key = f"evidences/{evidence_id}/thumbnail/{uuid.uuid4().hex}.png"
                put_object(key, preview, "image/png")
                keys.append(key)
                db.add(EvidenceVersion(evidence_id=evidence.id, version=1, storage_key=key,
                                       sha256=hashlib.sha256(preview).hexdigest(), size=len(preview),
                                       mime_type="image/png", author_id=actor.id, kind="thumbnail"))
            db.commit()
            db.refresh(evidence)
        except Exception:
            db.rollback()
            for key in keys:
                try:
                    delete_object(key)
                except Exception:
                    # Objects retain UUID scope; a retention sweep handles orphaned objects.
                    pass
            raise
    if mime.startswith("image/") and getattr(settings, "queue_enabled", False):
        from .jobs import enqueue_thumbnail
        enqueue_thumbnail(evidence.id)
    return evidence


def conflict(db: Session, evidence_id: str):
    db.rollback()
    current = db.get(Evidence, evidence_id)
    raise HTTPException(409, {"code": "version_conflict", "current_version": current.version if current else None})


def update_metadata(db: Session, actor: User, evidence: Evidence, patch: EvidencePatch):
    values = patch.model_dump(exclude_unset=True, exclude={"expected_version"})
    if "metadata" in values:
        user_metadata = values.pop("metadata")
        # Validated intrinsic dimensions/type cannot be forged through metadata edits.
        intrinsic = {key: value for key, value in evidence.metadata_json.items()
                     if key in {"width", "height", "frames", "detected_mime", "preview_policy", "encoding"}}
        values["metadata_json"] = {**(user_metadata or {}), **intrinsic}
    if "visibility" in values:
        if values["visibility"] == "team" and not evidence.team_id:
            raise HTTPException(422, "Evidência sem equipe")
        if values["visibility"] == "team" and evidence.team_id:
            # A autorização é reavaliada no momento da mutação. O antigo
            # proprietário não pode voltar a compartilhar após sair da equipe.
            authorize(db, actor, evidence, "edit")
            authorize_team(db, actor, evidence.team_id, "edit")
        if evidence.owner_id != actor.id and not actor.is_admin:
            raise HTTPException(403, "Somente proprietário pode alterar visibilidade")
        if values["visibility"] != evidence.visibility and db.scalar(
            select(WriteupEvidence.id).where(WriteupEvidence.evidence_id == evidence.id).limit(1)
        ):
            raise HTTPException(409, "Desassocie a evidência antes de alterar sua visibilidade")
    for required in ("name", "description", "origin", "tags", "visibility"):
        if required in values and values[required] is None:
            raise HTTPException(422, f"{required} não pode ser nulo")
    values.update(version=patch.expected_version + 1, updated_at=utcnow())
    result = db.execute(update(Evidence).where(Evidence.id == evidence.id,
                                               Evidence.version == patch.expected_version,
                                               Evidence.deleted_at.is_(None)).values(**values)
                        .execution_options(synchronize_session=False))
    if result.rowcount != 1:
        conflict(db, evidence.id)
    event(db, actor, evidence, "metadata_updated", {"fields": list(values), "version": patch.expected_version + 1})
    audit(db, actor, "evidence.metadata", "evidence", evidence.id, {"fields": list(values)})
    db.commit()
    db.refresh(evidence)
    return evidence


def annotate(db: Session, actor: User, evidence: Evidence, data: AnnotationCreate):
    if not evidence.mime_type.startswith("image/"):
        raise HTTPException(422, "Anotação visual exige imagem")
    if (data.data.width, data.data.height) != (evidence.metadata_json.get("width"), evidence.metadata_json.get("height")):
        raise HTTPException(422, "Dimensões não correspondem à evidência original")
    original = read_object(evidence.storage_key, max_bytes=settings.max_upload_bytes)
    if hashlib.sha256(original).hexdigest() != evidence.sha256:
        raise HTTPException(503, "Falha de integridade da evidência original")
    try:
        derived = render_annotation(original, data.data)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if len(derived) > settings.max_upload_bytes:
        raise HTTPException(413, "Imagem derivada acima do limite")
    result = db.execute(update(Evidence).where(Evidence.id == evidence.id,
                                               Evidence.version == data.expected_version,
                                               Evidence.deleted_at.is_(None))
                        .values(version=data.expected_version + 1, updated_at=utcnow())
                        .execution_options(synchronize_session=False))
    if result.rowcount != 1:
        conflict(db, evidence.id)
    version = data.expected_version + 1
    key = f"evidences/{evidence.id}/derived/{uuid.uuid4().hex}.png"
    annotation = EvidenceAnnotation(evidence_id=evidence.id, author_id=actor.id, version=version,
                                    data=data.data.model_dump(by_alias=True, exclude_none=True))
    derivative = EvidenceVersion(evidence_id=evidence.id, version=version, storage_key=key,
                                 sha256=hashlib.sha256(derived).hexdigest(), size=len(derived),
                                 mime_type="image/png", author_id=actor.id, kind="annotated")
    stored = False
    try:
        put_object(key, derived, "image/png")
        stored = True
        db.add_all([annotation, derivative])
        linked_ids = select(WriteupEvidence.writeup_id).where(WriteupEvidence.evidence_id == evidence.id)
        # Uma aprovação nunca cobre evidências visuais alteradas posteriormente.
        db.execute(update(Writeup).where(Writeup.id.in_(linked_ids))
                   .values(approved_revision=None, status="draft")
                   .execution_options(synchronize_session=False))
        db.execute(update(ReviewRequest).where(ReviewRequest.writeup_id.in_(linked_ids),
                                               ReviewRequest.status.in_(["pending", "approved"]))
                   .values(status="stale").execution_options(synchronize_session=False))
        event(db, actor, evidence, "annotation", {"version": version, "sha256": derivative.sha256,
                                                  "shape_count": len(data.data.shapes), "cropped": data.data.crop is not None})
        event(db, actor, evidence, "version_created", {"version": version, "kind": "annotated"})
        audit(db, actor, "evidence.annotate", "evidence", evidence.id, {"version": version})
        db.commit()
        db.refresh(evidence)
        db.refresh(annotation)
        db.refresh(derivative)
    except Exception:
        db.rollback()
        if stored:
            delete_object(key)
        raise
    return {"annotation": annotation_out(annotation), "version": version, "derived_version": version_out(derivative)}
