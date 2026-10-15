# SPDX-License-Identifier: MIT
import hashlib
import json
import logging
import uuid

from sqlalchemy import select, update

from app.config import settings
from app.db import SessionLocal, utcnow
from app.models import AIJob, Evidence, Export, User, Writeup
from app.security import audit, authorize
from app.modules.evidence.storage import put_object
from app.modules.studio.ai import generate_result
from app.modules.studio.exporting import export_document

logger = logging.getLogger(__name__)


def enqueue(kind, record_id):
    function = execute_export if kind == "export" else execute_ai
    if not settings.queue_enabled or settings.queue_eager:
        function(record_id)
        return
    from redis import Redis
    from rq import Queue, Retry
    connection = Redis.from_url(settings.redis_url, socket_timeout=5, socket_connect_timeout=5)
    connection.ping()
    queue = Queue(settings.queue_name, connection=connection)
    timeout = settings.export_job_timeout if kind == "export" else settings.ai_timeout_seconds + 30
    queue.enqueue(function, record_id, job_id=f"{kind}-{record_id}", job_timeout=timeout,
                  result_ttl=3600, failure_ttl=86400, retry=Retry(max=2, interval=[5, 15]),
                  on_failure=worker_failure, meta={"record_id": record_id, "kind": kind})


def worker_failure(job, _connection, _type, _value, _traceback):
    """Includes RQ hard timeouts: domain state cannot remain falsely running."""
    model = Export if job.meta.get("kind") == "export" else AIJob
    with SessionLocal() as db:
        row = db.get(model, job.meta.get("record_id"))
        if row and row.status != "completed":
            row.status = "cancelled" if row.cancel_requested else "failed"
            row.error = "Job interrompido pelo worker; consulte os logs com o identificador do job"
            row.updated_at = utcnow()
            db.commit()


def _claim(db, model, record_id):
    updated = db.execute(update(model).where(model.id == record_id,
                        model.status.in_(["queued", "failed"]), model.cancel_requested.is_(False))
                         .values(status="running", error=None, updated_at=utcnow()))
    db.commit()
    return updated.rowcount == 1


def _actor(db, actor_id):
    actor = db.get(User, actor_id)
    if not actor or not actor.is_active:
        raise ValueError("Usuário não está mais ativo")
    return actor


def execute_export(record_id):
    with SessionLocal() as db:
        if not _claim(db, Export, record_id):
            return
        row = db.get(Export, record_id)
        try:
            actor = _actor(db, row.requested_by)
            document = db.get(Writeup, row.writeup_id)
            authorize(db, actor, document, "read")
            snapshot = row.options["snapshot"]
            for manifest in snapshot.get("evidences", []):
                evidence = db.get(Evidence, manifest["id"])
                authorize(db, actor, evidence, "read")
                if row.options.get("include_originals") and evidence.owner_id != actor.id and not actor.is_admin:
                    raise ValueError("Exportação de originais não está mais autorizada")
            data, mime, filename = export_document(snapshot, row.options)
            if len(data) > settings.max_export_bytes:
                raise ValueError("Exportação excede o limite configurado")
            db.refresh(row)
            if row.cancel_requested:
                row.status = "cancelled"
            else:
                key = f"exports/{uuid.uuid4()}/{filename}"
                put_object(key, data, mime)
                row.storage_key = key
                row.options = {**row.options, "mime_type": mime, "filename": filename,
                               "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
                row.status = "completed"
                audit(db, actor, "export.completed", "export", row.id, {"version": row.version, "format": row.format})
            row.updated_at = utcnow()
            db.commit()
        except Exception as exc:
            logger.error("export_failed", extra={"job_id": record_id, "exception_type": type(exc).__name__})
            db.rollback()
            row = db.get(Export, record_id)
            row.status = "cancelled" if row.cancel_requested else "failed"
            row.error = "Falha ao gerar exportação; consulte os logs pelo ID do job"
            row.updated_at = utcnow()
            db.commit()


def execute_ai(record_id):
    with SessionLocal() as db:
        if not _claim(db, AIJob, record_id):
            return
        row = db.get(AIJob, record_id)
        try:
            if not settings.ai_enabled:
                raise ValueError("IA desabilitada")
            actor = _actor(db, row.owner_id)
            if row.writeup_id:
                authorize(db, actor, db.get(Writeup, row.writeup_id), "read")
            for evidence_id in row.input_data.get("evidence_ids", []):
                authorize(db, actor, db.get(Evidence, evidence_id), "read")
            if row.provider == "external" and (not row.external_consent or not settings.ai_external_enabled):
                raise ValueError("Envio externo não autorizado")
            result = generate_result(row.task, row.provider, row.input_data["sources"])
            db.refresh(row)
            if row.cancel_requested:
                row.status = "cancelled"
                row.output_data = None
            else:
                row.output_data = result
                row.status = "completed"
                audit(db, actor, "ai.completed", "ai_job", row.id,
                      {"provider": row.provider, "human_review_required": True})
            row.updated_at = utcnow()
            db.commit()
        except Exception as exc:
            logger.error("ai_failed", extra={"job_id": record_id, "exception_type": type(exc).__name__})
            db.rollback()
            row = db.get(AIJob, record_id)
            row.status = "cancelled" if row.cancel_requested else "failed"
            row.error = "Falha no provedor de IA; consulte os logs pelo ID do job"
            row.updated_at = utcnow()
            db.commit()


def cancel_job(db, row, kind):
    row.cancel_requested = True
    if row.status in {"queued", "failed"}:
        row.status = "cancelled"
    row.updated_at = utcnow()
    db.commit()
    if settings.queue_enabled:
        from redis import Redis
        from rq.job import Job
        from rq.exceptions import NoSuchJobError
        try:
            job = Job.fetch(f"{kind}-{row.id}", connection=Redis.from_url(settings.redis_url,
                socket_timeout=5, socket_connect_timeout=5))
            if job.get_status() in {"queued", "deferred", "scheduled"}:
                job.cancel()
        except NoSuchJobError:
            pass
        except Exception:
            logger.warning("queue_cancel_unavailable", extra={"job_id": row.id})
