# SPDX-License-Identifier: MIT
import copy
import hashlib
import re
import uuid

from fastapi import HTTPException
from sqlalchemy import select, update

from app.db import utcnow
from app.models import Evidence, EvidenceEvent, EvidenceVersion, Publication, ReviewRequest, Writeup, WriteupEvidence
from app.modules.evidence.storage import put_object, read_object
from app.modules.studio.exporting import sanitize_markdown
from app.security import audit, authorize


def linked_evidence(db, writeup_id):
    return db.scalars(select(Evidence).join(WriteupEvidence, WriteupEvidence.evidence_id == Evidence.id)
        .where(WriteupEvidence.writeup_id == writeup_id, Evidence.deleted_at.is_(None))
        .order_by(WriteupEvidence.position, Evidence.id)).all()


def evidence_manifest(db, actor, evidence):
    authorize(db, actor, evidence, "read")
    derived = db.scalar(select(EvidenceVersion).where(EvidenceVersion.evidence_id == evidence.id,
                         EvidenceVersion.kind == "annotated").order_by(EvidenceVersion.version.desc()))
    return {"id": evidence.id, "name": evidence.name, "origin": evidence.origin,
            "sha256": derived.sha256 if derived else evidence.sha256,
            "mime_type": derived.mime_type if derived else evidence.mime_type,
            "storage_key": derived.storage_key if derived else evidence.storage_key,
            "original_key": evidence.storage_key, "derived": bool(derived),
            "version": derived.version if derived else 1,
            "captured_at": evidence.captured_at.isoformat() if evidence.captured_at else None,
            "received_at": evidence.received_at.isoformat()}


def freeze_export(db, actor, writeup, options):
    evidences = []
    if options.include_evidences or options.include_originals:
        for evidence in linked_evidence(db, writeup.id):
            if options.include_originals and evidence.owner_id != actor.id and not actor.is_admin:
                raise HTTPException(403, "Exportação de originais exige proprietário ou administrador")
            evidences.append(evidence_manifest(db, actor, evidence))
    return {"title": writeup.title, "document": copy.deepcopy(writeup.document),
            "version": writeup.version, "created_at": utcnow().isoformat(), "evidences": evidences}


def sanitized_public_document(document, selected_ids):
    result = copy.deepcopy(document)
    selected = set(selected_ids)
    for section in result["sections"]:
        markdown = sanitize_markdown(section["markdown"])
        def replace_image(match):
            source = match.group(2)
            linked_id = re.fullmatch(r"(?:evidence:|/api/v1/evidences/)([a-fA-F0-9-]{36})(?:/download)?", source)
            if linked_id and linked_id.group(1) in selected:
                return f"![{match.group(1)}](evidence:{linked_id.group(1)})"
            return "[Imagem omitida da publicação]"
        markdown = re.sub(r"!\[([^\]]*)\]\(([^\s)]+)(?:\s+[^)]*)?\)", replace_image, markdown)
        def replace_reference(match):
            evidence_id = match.group(1)
            return "evidence:" + evidence_id if evidence_id in selected else "[evidência privada omitida]"
        markdown = re.sub(r"(?:evidence:|/api/v1/evidences/)([a-fA-F0-9-]{36})(?:/download)?", replace_reference, markdown)
        markdown = re.sub(r"\[([^\]]*)\]\((/(?:api/v1/)?(?:writeups|challenges|competitions|evidences)[^)]*)\)", r"\1 [link interno omitido]", markdown)
        section["markdown"] = markdown
    return result


def publish_snapshot(db, actor, writeup, data):
    authorize(db, actor, writeup, "publish")
    if data.visibility == "public" and not data.confirm_public:
        raise HTTPException(422, "Confirme explicitamente a publicação pública")
    if data.visibility == "team" and not writeup.team_id:
        raise HTTPException(422, "Publicação de equipe exige writeup associado à equipe")
    if data.expires_at and (data.expires_at.tzinfo is None or data.expires_at <= utcnow()):
        raise HTTPException(422, "Expiração deve estar no futuro e incluir fuso horário")
    review = db.scalar(select(ReviewRequest).where(
        ReviewRequest.writeup_id == writeup.id, ReviewRequest.version == data.expected_version,
        ReviewRequest.status == "approved", ReviewRequest.reviewer_id != writeup.owner_id))
    if not review or writeup.approved_revision != data.expected_version:
        raise HTTPException(409, "A revisão atual precisa de aprovação de outro usuário")
    selected = []
    linked_ids = {row.id for row in linked_evidence(db, writeup.id)}
    for evidence_id in dict.fromkeys(data.evidence_ids):
        if evidence_id not in linked_ids:
            raise HTTPException(422, "Evidência deve estar associada ao writeup")
        evidence = db.get(Evidence, evidence_id)
        manifest = evidence_manifest(db, actor, evidence)
        if data.visibility == "public":
            if evidence.owner_id != actor.id and not actor.is_admin:
                raise HTTPException(403, "Somente o proprietário pode compartilhar uma evidência publicamente")
            if not manifest["derived"]:
                raise HTTPException(422, "Publicação pública exige versão anotada; o original permanece protegido")
        selected.append(manifest)
    publication_id = str(uuid.uuid4())
    updated = db.execute(update(Writeup).where(
        Writeup.id == writeup.id, Writeup.version == data.expected_version,
        Writeup.approved_revision == data.expected_version, Writeup.deleted_at.is_(None)
    ).values(published_at=utcnow(), status="published").execution_options(synchronize_session=False))
    if updated.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "Writeup alterado antes da publicação")
    public_manifests = []
    for item in selected:
        content = read_object(item["storage_key"], max_bytes=20971520)
        key = f"publications/{publication_id}/{uuid.uuid4()}"
        put_object(key, content, item["mime_type"])
        public_manifests.append({key_name: item[key_name] for key_name in
            ["id", "name", "sha256", "mime_type", "version", "captured_at", "received_at"]} | {"storage_key": key})
        db.add(EvidenceEvent(evidence_id=item["id"], actor_id=actor.id, event_type="publication",
                             details={"writeup_id": writeup.id, "publication_id": publication_id}))
    document = sanitized_public_document(writeup.document, data.evidence_ids) if data.visibility == "public" else copy.deepcopy(writeup.document)
    publication = Publication(id=publication_id, writeup_id=writeup.id, owner_id=writeup.owner_id,
                              team_id=writeup.team_id, version=data.expected_version, title=writeup.title,
                              document=document, visibility=data.visibility, expires_at=data.expires_at,
                              evidence_manifest=public_manifests)
    db.add(publication)
    audit(db, actor, "writeup.published", "publication", publication_id,
          {"visibility": data.visibility, "version": data.expected_version,
           "evidence_ids": data.evidence_ids, "explicit_public_confirmation": data.confirm_public})
    db.commit()
    return publication


def publication_out(row):
    return {"id": row.id, "writeup_id": row.writeup_id, "title": row.title, "version": row.version,
            "document": row.document, "visibility": row.visibility, "created_at": row.created_at,
            "expires_at": row.expires_at, "evidences": [
                {key: value for key, value in item.items() if key != "storage_key"}
                for item in row.evidence_manifest]}
