# SPDX-License-Identifier: MIT
"""Miniaturas RQ idempotentes. Originais permanecem imutáveis."""
from __future__ import annotations

import hashlib
import logging
import uuid

from sqlalchemy import select

from app.config import settings
from app.db import SessionLocal
from app.models import Evidence, EvidenceEvent, EvidenceVersion

from .rendering import thumbnail
from .storage import delete_object, put_object, read_object

logger = logging.getLogger(__name__)


def generate_thumbnail(evidence_id: str):
    with SessionLocal() as db:
        evidence = db.get(Evidence, evidence_id)
        if not evidence or evidence.deleted_at is not None or not evidence.mime_type.startswith("image/"):
            return
        exists = db.scalar(select(EvidenceVersion.id).where(EvidenceVersion.evidence_id == evidence.id,
                                                            EvidenceVersion.kind == "thumbnail").limit(1))
        if exists:
            return
        original = read_object(evidence.storage_key, max_bytes=settings.max_upload_bytes)
        if hashlib.sha256(original).hexdigest() != evidence.sha256:
            raise RuntimeError("Hash original inválido")
        result = thumbnail(original)
        key = f"evidences/{evidence.id}/thumbnail/{uuid.uuid4().hex}.png"
        stored = False
        try:
            put_object(key, result, "image/png")
            stored = True
            db.add(EvidenceVersion(evidence_id=evidence.id, version=1, storage_key=key,
                                   sha256=hashlib.sha256(result).hexdigest(), size=len(result), mime_type="image/png",
                                   author_id=evidence.owner_id, kind="thumbnail"))
            db.add(EvidenceEvent(evidence_id=evidence.id, actor_id=evidence.owner_id,
                                 event_type="thumbnail_created", details={"processing": "background"}))
            db.commit()
        except Exception:
            db.rollback()
            if stored:
                delete_object(key)
            raise


def enqueue_thumbnail(evidence_id: str):
    if settings.queue_eager:
        generate_thumbnail(evidence_id)
        return
    try:
        from redis import Redis
        from rq import Queue, Retry
        queue = Queue(settings.queue_name, connection=Redis.from_url(settings.redis_url), default_timeout=120)
        queue.enqueue(generate_thumbnail, evidence_id, job_id=f"thumbnail-{evidence_id}",
                      retry=Retry(max=2, interval=[10, 30]), result_ttl=3600, failure_ttl=86400)
    except Exception:
        # A queue outage must not make a successfully persisted original appear lost.
        logger.exception("thumbnail_queue_unavailable", extra={"evidence_id": evidence_id})
        generate_thumbnail(evidence_id)
