# SPDX-License-Identifier: MIT
import hashlib
import json
import re

from fastapi import HTTPException

from app.config import settings
from app.models import Evidence
from app.modules.evidence.storage import read_object
from app.modules.studio.services import get_writeup
from app.security import authorize


def authorized_sources(db, actor, data):
    sources = []
    writeup = get_writeup(db, actor, data.writeup_id) if data.writeup_id else None
    if data.notes:
        sources.append({"source_id": "submitted-notes", "kind": "user_notes",
                        "sha256": hashlib.sha256(data.notes.encode()).hexdigest(), "text": data.notes})
    if writeup:
        text = "\n\n".join(section["title"] + "\n" + section["markdown"] for section in writeup.document["sections"])
        sources.append({"source_id": "writeup:" + writeup.id, "kind": "writeup",
                        "version": writeup.version, "sha256": hashlib.sha256(text.encode()).hexdigest(), "text": text})
    query_terms = set(re.findall(r"\w{3,}", data.notes.lower()))
    for evidence_id in dict.fromkeys(data.evidence_ids):
        evidence = db.get(Evidence, evidence_id)
        authorize(db, actor, evidence, "read")
        text = evidence.description
        if evidence.mime_type in {"text/plain", "text/csv", "application/json"} and evidence.size <= 1048576:
            content = read_object(evidence.storage_key, max_bytes=1048576).decode("utf-8", errors="replace")
            # Scoped lexical retrieval; user supplied evidence IDs are authorized first.
            chunks = [content[index:index + 3000] for index in range(0, len(content), 3000)]
            chunks.sort(key=lambda chunk: len(query_terms & set(re.findall(r"\w{3,}", chunk.lower()))), reverse=True)
            text = "\n".join(chunks[:8])
        sources.append({"source_id": "evidence:" + evidence.id, "kind": "evidence",
                        "name": evidence.name, "sha256": evidence.sha256, "origin": evidence.origin,
                        "captured_at": evidence.captured_at.isoformat() if evidence.captured_at else None,
                        "received_at": evidence.received_at.isoformat(), "text": text})
    if not sources:
        raise HTTPException(422, "Forneça notas ou fontes autorizadas")
    if len(json.dumps(sources, ensure_ascii=False)) > settings.ai_max_input_chars:
        raise HTTPException(413, "Contexto de IA excede o limite configurado")
    return sources, writeup
