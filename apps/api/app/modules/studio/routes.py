# SPDX-License-Identifier: MIT
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db, utcnow
from app.models import AIJob, Challenge, Evidence, EvidenceEvent, Export, Publication, User, Writeup, WriteupEvidence, WriteupRevision, WriteupTemplate
from app.modules.evidence.storage import object_response
from app.modules.studio.ai_service import authorized_sources
from app.modules.studio.jobs import cancel_job, enqueue
from app.modules.studio.policy import compatible_scope, validate_team
from app.modules.studio.repository import paginate, visible_writeups
from app.modules.studio.schemas import AIInput, EvidenceLink, ExportInput, PublishInput, RestoreInput, WriteupCreate, WriteupUpdate
from app.modules.studio.services import canonical_document, get_writeup, revision_diff, revision_out, save_revision, writeup_out
from app.modules.studio.snapshots import freeze_export, linked_evidence, publication_out, publish_snapshot
from app.security import audit, authorize, get_actor, require_csrf, visible_query

router = APIRouter(tags=["Writeup Studio, exportações e IA"])
DB = Annotated[Session, Depends(get_db)]
Actor = Annotated[User, Depends(get_actor)]
Mutator = Annotated[User, Depends(require_csrf)]

STANDARD_SECTIONS = ["Informações do desafio", "Objetivo", "Contexto", "Ambiente", "Reconhecimento e análise",
    "Hipóteses", "Metodologia utilizada", "Etapas técnicas", "Comandos executados", "Resultados observados",
    "Evidências", "Exploração ou resolução", "Validação", "Flag", "Conclusão", "Lições aprendidas", "Referências"]


@router.get("/writeups")
def list_writeups(db: DB, actor: Actor, page: int = Query(1, ge=1), page_size: int = Query(30, ge=1, le=100),
                  challenge_id: str | None = None, status: str | None = None, q: str | None = Query(None, max_length=200)):
    statement = visible_writeups(db, actor)
    if challenge_id:
        statement = statement.where(Writeup.challenge_id == challenge_id)
    if status:
        statement = statement.where(Writeup.status == status)
    if q:
        statement = statement.where(Writeup.title.ilike("%" + q.replace("%", "\\%").replace("_", "\\_") + "%", escape="\\"))
    return paginate(db, statement.order_by(Writeup.updated_at.desc(), Writeup.id), page, page_size, writeup_out)


@router.post("/writeups", status_code=201)
def create_writeup(data: WriteupCreate, db: DB, actor: Mutator):
    validate_team(db, actor, data.team_id, data.visibility)
    if data.challenge_id:
        challenge = db.get(Challenge, data.challenge_id)
        authorize(db, actor, challenge, "read")
        if data.visibility == "team" and (challenge.visibility != "team" or challenge.team_id != data.team_id):
            raise HTTPException(422, "Desafio deve pertencer à mesma equipe do writeup")
    document = data.document.model_dump() if data.document else {
        "schema_version": 1, "sections": [{"id": "section-" + str(index), "title": title, "markdown": ""}
                                          for index, title in enumerate(STANDARD_SECTIONS, 1)]}
    if data.template_id:
        if data.document is not None:
            raise HTTPException(422, "Escolha document ou template_id")
        template = db.get(WriteupTemplate, data.template_id)
        authorize(db, actor, template, "read")
        document = template.document
    row = Writeup(owner_id=actor.id, team_id=data.team_id, challenge_id=data.challenge_id,
                  title=data.title, document=canonical_document(document), visibility=data.visibility,
                  tags=data.tags, tools=data.tools, languages=data.languages, version=1)
    db.add(row); db.flush()
    db.add(WriteupRevision(writeup_id=row.id, version=1, title=row.title, document=row.document,
                          author_id=actor.id, message="Documento criado"))
    audit(db, actor, "writeup.created", "writeup", row.id)
    db.commit(); db.refresh(row)
    return writeup_out(row)


@router.get("/writeups/{writeup_id}")
def retrieve_writeup(writeup_id: str, db: DB, actor: Actor):
    return writeup_out(get_writeup(db, actor, writeup_id))


@router.patch("/writeups/{writeup_id}")
def update_writeup(writeup_id: str, data: WriteupUpdate, db: DB, actor: Mutator):
    row = get_writeup(db, actor, writeup_id, "write")
    changes = data.model_dump(exclude_none=True, exclude={"expected_version", "message"})
    visibility = changes.get("visibility", row.visibility)
    validate_team(db, actor, row.team_id, visibility)
    if visibility != row.visibility:
        authorize(db, actor, row, "manage")
        for evidence in linked_evidence(db, row.id):
            if visibility == "team" and (evidence.visibility != "team" or evidence.team_id != row.team_id):
                raise HTTPException(422, "Remova ou compartilhe evidências privadas antes de compartilhar o writeup")
    return writeup_out(save_revision(db, actor, row, data.expected_version, changes, data.message))


@router.delete("/writeups/{writeup_id}")
def delete_writeup(writeup_id: str, db: DB, actor: Mutator, expected_version: int = Query(..., ge=1)):
    row = get_writeup(db, actor, writeup_id, "delete")
    result = db.execute(update(Writeup).where(Writeup.id == row.id, Writeup.version == expected_version,
        Writeup.deleted_at.is_(None)).values(deleted_at=utcnow(), approved_revision=None,
        version=expected_version + 1).execution_options(synchronize_session=False))
    if result.rowcount != 1:
        db.rollback(); raise HTTPException(409, "Writeup alterado; atualize antes de excluir")
    db.execute(update(Publication).where(Publication.writeup_id == row.id).values(expires_at=utcnow()))
    audit(db, actor, "writeup.deleted", "writeup", row.id)
    db.commit()
    return {"ok": True}


@router.get("/writeups/{writeup_id}/revisions")
def revisions(writeup_id: str, db: DB, actor: Actor, page: int = Query(1, ge=1), page_size: int = Query(30, ge=1, le=100)):
    get_writeup(db, actor, writeup_id)
    return paginate(db, select(WriteupRevision).where(WriteupRevision.writeup_id == writeup_id)
        .order_by(WriteupRevision.version.desc()), page, page_size, revision_out)


@router.post("/writeups/{writeup_id}/revisions/{revision_id}/restore")
def restore(writeup_id: str, revision_id: str, data: RestoreInput, db: DB, actor: Mutator):
    row = get_writeup(db, actor, writeup_id, "write")
    revision = db.get(WriteupRevision, revision_id)
    if not revision or revision.writeup_id != row.id:
        raise HTTPException(404, "Revisão não encontrada")
    return writeup_out(save_revision(db, actor, row, data.expected_version,
        {"title": revision.title, "document": revision.document, "status": "draft"},
        f"Restauração da versão {revision.version}"))


@router.get("/writeups/{writeup_id}/diff")
def diff(writeup_id: str, db: DB, actor: Actor, from_version: int = Query(..., ge=1), to_version: int = Query(..., ge=1)):
    get_writeup(db, actor, writeup_id)
    rows = {row.version: row for row in db.scalars(select(WriteupRevision).where(
        WriteupRevision.writeup_id == writeup_id, WriteupRevision.version.in_([from_version, to_version])))}
    if from_version not in rows or to_version not in rows:
        raise HTTPException(404, "Revisão não encontrada")
    return {"from_version": from_version, "to_version": to_version,
            "diff": revision_diff(rows[from_version], rows[to_version])}


@router.get("/writeups/{writeup_id}/evidences")
def writeup_evidences(writeup_id: str, db: DB, actor: Actor):
    get_writeup(db, actor, writeup_id)
    rows = db.execute(select(WriteupEvidence, Evidence).join(Evidence, Evidence.id == WriteupEvidence.evidence_id)
        .where(WriteupEvidence.writeup_id == writeup_id, Evidence.deleted_at.is_(None))
        .order_by(WriteupEvidence.position, WriteupEvidence.id)).all()
    items = []
    for relation, evidence in rows:
        authorize(db, actor, evidence, "read")
        items.append({"id": relation.id, "evidence_id": evidence.id, "name": evidence.name,
                      "mime_type": evidence.mime_type, "sha256": evidence.sha256, "section_id": relation.section_id,
                      "position": relation.position, "version": evidence.version})
    return {"items": items, "total": len(items), "page": 1, "page_size": len(items)}


@router.post("/writeups/{writeup_id}/evidences", status_code=201)
def link_evidence(writeup_id: str, data: EvidenceLink, db: DB, actor: Mutator):
    row = get_writeup(db, actor, writeup_id, "write")
    evidence = db.get(Evidence, data.evidence_id)
    compatible_scope(db, actor, row, evidence)
    if data.section_id and data.section_id not in {section["id"] for section in row.document["sections"]}:
        raise HTTPException(422, "Seção não encontrada no documento")
    relation = db.scalar(select(WriteupEvidence).where(WriteupEvidence.writeup_id == row.id,
                            WriteupEvidence.evidence_id == data.evidence_id))
    if relation:
        relation.section_id, relation.position = data.section_id, data.position
    else:
        relation = WriteupEvidence(writeup_id=row.id, **data.model_dump())
        db.add(relation)
    db.add(EvidenceEvent(evidence_id=evidence.id, actor_id=actor.id, event_type="inclusion",
                         details={"writeup_id": row.id, "section_id": data.section_id}))
    saved = save_revision(db, actor, row, row.version, {}, "Associação de evidência")
    return {"id": relation.id, "evidence_id": evidence.id, "section_id": relation.section_id,
            "position": relation.position, "writeup_version": saved.version}


@router.delete("/writeups/{writeup_id}/evidences/{evidence_id}")
def unlink_evidence(writeup_id: str, evidence_id: str, db: DB, actor: Mutator):
    row = get_writeup(db, actor, writeup_id, "write")
    relation = db.scalar(select(WriteupEvidence).where(WriteupEvidence.writeup_id == row.id,
                            WriteupEvidence.evidence_id == evidence_id))
    if not relation:
        raise HTTPException(404, "Associação não encontrada")
    db.delete(relation)
    db.add(EvidenceEvent(evidence_id=evidence_id, actor_id=actor.id, event_type="association_removed",
                         details={"writeup_id": row.id}))
    saved = save_revision(db, actor, row, row.version, {}, "Remoção de evidência")
    return {"ok": True, "writeup_version": saved.version}


def export_out(row):
    return {"id": row.id, "writeup_id": row.writeup_id, "format": row.format, "status": row.status,
            "version": row.version, "error": row.error, "created_at": row.created_at, "updated_at": row.updated_at,
            "cancel_requested": row.cancel_requested, "filename": row.options.get("filename"),
            "sha256": row.options.get("sha256"), "size": row.options.get("size")}


def get_export(db, actor, export_id):
    row = db.get(Export, export_id)
    if not row or (row.requested_by != actor.id and not actor.is_admin):
        raise HTTPException(404, "Exportação não encontrada")
    get_writeup(db, actor, row.writeup_id)
    return row


@router.post("/writeups/{writeup_id}/exports", status_code=202)
def request_export(writeup_id: str, data: ExportInput, db: DB, actor: Mutator):
    writeup = get_writeup(db, actor, writeup_id)
    snapshot = freeze_export(db, actor, writeup, data)
    row = Export(writeup_id=writeup.id, requested_by=actor.id, format=data.format,
                 version=writeup.version, options={**data.model_dump(), "snapshot": snapshot})
    db.add(row); db.flush()
    audit(db, actor, "export.requested", "export", row.id,
          {"include_originals": data.include_originals, "version": row.version})
    db.commit()
    try:
        enqueue("export", row.id)
    except Exception:
        row.status, row.error = "failed", "Fila indisponível; tente novamente"
        db.commit()
        raise HTTPException(503, {"message": row.error, "export_id": row.id})
    db.refresh(row)
    return export_out(row)


@router.get("/exports/{export_id}")
def export_status(export_id: str, db: DB, actor: Actor):
    return export_out(get_export(db, actor, export_id))


@router.get("/exports/{export_id}/download")
def export_download(export_id: str, db: DB, actor: Actor):
    row = get_export(db, actor, export_id)
    if row.status != "completed" or not row.storage_key:
        raise HTTPException(409, "Exportação ainda não está disponível")
    for manifest in row.options["snapshot"].get("evidences", []):
        evidence = db.get(Evidence, manifest["id"])
        authorize(db, actor, evidence, "read")
        if row.options.get("include_originals") and evidence.owner_id != actor.id and not actor.is_admin:
            raise HTTPException(403, "Originais não autorizados")
    return object_response(row.storage_key, row.options["mime_type"], row.options["filename"])


@router.post("/exports/{export_id}/cancel")
def export_cancel(export_id: str, db: DB, actor: Mutator):
    row = get_export(db, actor, export_id)
    if row.status == "completed":
        raise HTTPException(409, "Exportação já concluída")
    cancel_job(db, row, "export")
    return export_out(row)


@router.post("/writeups/{writeup_id}/publish", status_code=201)
def publish(writeup_id: str, data: PublishInput, db: DB, actor: Mutator):
    row = get_writeup(db, actor, writeup_id, "publish")
    result = publication_out(publish_snapshot(db, actor, row, data))
    result["url"] = ("/public/writeups/" if data.visibility == "public" else "/publications/") + result["id"]
    return result


def get_publication(db, publication_id, public=False, actor=None):
    row = db.get(Publication, publication_id)
    if not row or (row.expires_at and row.expires_at <= utcnow()):
        raise HTTPException(404, "Publicação indisponível")
    if public and row.visibility != "public":
        raise HTTPException(404, "Publicação indisponível")
    if not public:
        authorize(db, actor, row, "read")
    return row


@router.get("/public/writeups/{publication_id}")
def public_writeup(publication_id: str, db: DB):
    return publication_out(get_publication(db, publication_id, public=True))


@router.get("/public/writeups/{publication_id}/evidences/{evidence_id}")
def public_evidence(publication_id: str, evidence_id: str, db: DB):
    row = get_publication(db, publication_id, public=True)
    item = next((item for item in row.evidence_manifest if item["id"] == evidence_id), None)
    if not item:
        raise HTTPException(404, "Evidência indisponível")
    return object_response(item["storage_key"], item["mime_type"], item["name"], inline=True)


@router.get("/publications/{publication_id}")
def private_publication(publication_id: str, db: DB, actor: Actor):
    return publication_out(get_publication(db, publication_id, actor=actor))


@router.delete("/publications/{publication_id}")
def revoke_publication(publication_id: str, db: DB, actor: Mutator):
    row = get_publication(db, publication_id, actor=actor)
    authorize(db, actor, row, "publish")
    row.expires_at = utcnow()
    audit(db, actor, "publication.revoked", "publication", row.id)
    db.commit()
    return {"ok": True}


def ai_out(row):
    return {"id": row.id, "owner_id": row.owner_id, "writeup_id": row.writeup_id,
            "task": row.task, "provider": row.provider, "status": row.status,
            "output_data": row.output_data, "error": row.error, "created_at": row.created_at,
            "updated_at": row.updated_at, "cancel_requested": row.cancel_requested,
            "human_review_required": True, "config_snapshot": row.config_snapshot}


def get_ai_job(db, actor, job_id):
    row = db.get(AIJob, job_id)
    if not row or (row.owner_id != actor.id and not actor.is_admin):
        raise HTTPException(404, "Job não encontrado")
    if row.writeup_id:
        get_writeup(db, actor, row.writeup_id)
    for evidence_id in row.input_data.get("evidence_ids", []):
        authorize(db, actor, db.get(Evidence, evidence_id), "read")
    return row


@router.get("/ai/providers")
def providers(actor: Actor):
    return {"enabled": settings.ai_enabled, "providers": [
        {"name": "ollama", "enabled": settings.ai_enabled, "local": True, "model": settings.ollama_model},
        {"name": "external", "enabled": settings.ai_enabled and settings.ai_external_enabled,
         "local": False, "requires_explicit_consent": True}], "human_review_required": True}


@router.post("/ai/jobs", status_code=202)
def create_ai_job(data: AIInput, db: DB, actor: Mutator):
    if not settings.ai_enabled:
        raise HTTPException(503, "IA desabilitada pela operação")
    if data.provider == "external" and (not settings.ai_external_enabled or not data.external_consent):
        raise HTTPException(403, "Provedor externo exige habilitação pela operação e consentimento explícito")
    count = db.scalar(select(func.count()).select_from(AIJob).where(
        AIJob.owner_id == actor.id, AIJob.created_at >= utcnow() - timedelta(hours=1))) or 0
    if count >= settings.ai_max_jobs_per_hour:
        raise HTTPException(429, "Limite de jobs de IA por hora atingido")
    sources, writeup = authorized_sources(db, actor, data)
    row = AIJob(owner_id=actor.id, team_id=writeup.team_id if writeup else None,
                writeup_id=data.writeup_id, task=data.task, provider=data.provider,
                input_data={"sources": sources, "evidence_ids": data.evidence_ids},
                external_consent=data.external_consent, config_snapshot={
                    "model": settings.ollama_model if data.provider == "ollama" else settings.ai_external_model,
                    "provider": data.provider, "temperature": 0.1, "timeout_seconds": settings.ai_timeout_seconds,
                    "external_consent": data.external_consent, "human_review_required": True})
    db.add(row); db.flush()
    audit(db, actor, "ai.requested", "ai_job", row.id, {"provider": row.provider, "external_consent": row.external_consent})
    db.commit()
    try:
        enqueue("ai", row.id)
    except Exception:
        row.status, row.error = "failed", "Fila indisponível; tente novamente"
        db.commit()
        raise HTTPException(503, {"message": row.error, "job_id": row.id})
    db.refresh(row)
    return ai_out(row)


@router.get("/ai/jobs")
def list_ai_jobs(db: DB, actor: Actor, page: int = Query(1, ge=1), page_size: int = Query(30, ge=1, le=100)):
    statement = select(AIJob)
    if not actor.is_admin:
        statement = statement.where(AIJob.owner_id == actor.id)
    # Listing cannot bypass source revocation; filter the same scoped relations.
    visible_ids = visible_query(select(Writeup.id), Writeup, actor, db)
    statement = statement.where((AIJob.writeup_id.is_(None)) | AIJob.writeup_id.in_(visible_ids))
    result = paginate(db, statement.order_by(AIJob.created_at.desc()), page, page_size, ai_out)
    filtered = []
    for item in result["items"]:
        try:
            get_ai_job(db, actor, item["id"])
            filtered.append(item)
        except HTTPException:
            pass
    result["items"] = filtered
    return result


@router.get("/ai/jobs/{job_id}")
def ai_status(job_id: str, db: DB, actor: Actor):
    return ai_out(get_ai_job(db, actor, job_id))


@router.post("/ai/jobs/{job_id}/cancel")
def ai_cancel(job_id: str, db: DB, actor: Mutator):
    row = get_ai_job(db, actor, job_id)
    if row.status == "completed":
        raise HTTPException(409, "Job já concluído")
    cancel_job(db, row, "ai")
    return ai_out(row)
