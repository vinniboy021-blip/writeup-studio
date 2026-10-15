# SPDX-License-Identifier: MIT
from datetime import datetime, timezone
import difflib
import json

from fastapi import HTTPException
from sqlalchemy import select, update

from app.config import settings
from app.models import ReviewRequest, Writeup, WriteupRevision
from app.schemas import Document
from app.security import audit, authorize


def utcnow():
    return datetime.now(timezone.utc)


def get_writeup(db, actor, writeup_id, action="read"):
    row = db.get(Writeup, writeup_id)
    if not row or row.deleted_at:
        raise HTTPException(404, "Writeup não encontrado")
    authorize(db, actor, row, action)
    return row


def canonical_document(value):
    result = Document.model_validate(value).model_dump(mode="json")
    if len(json.dumps(result, ensure_ascii=False).encode()) > getattr(settings, "max_document_bytes", 2097152):
        raise HTTPException(413, "Documento excede o limite configurado")
    return result


def writeup_out(row):
    return {key: getattr(row, key) for key in (
        "id", "owner_id", "team_id", "challenge_id", "title", "document", "status",
        "visibility", "version", "approved_revision", "published_at", "created_at", "updated_at", "tags", "tools", "languages"
    )}


def revision_out(row):
    return {key: getattr(row, key) for key in (
        "id", "writeup_id", "version", "title", "document", "author_id", "message", "created_at"
    )}


def save_revision(db, actor, row, expected_version, changes, message=""):
    """CAS and immutable snapshot in one transaction. No read/check/write race."""
    authorize(db, actor, row, "write")
    values = {key: value for key, value in changes.items()
              if key in {"title", "document", "status", "visibility", "tags", "tools", "languages"}}
    if "document" in values:
        values["document"] = canonical_document(values["document"])
    title = values.get("title", row.title)
    document = values.get("document", row.document)
    next_version = expected_version + 1
    values.update(version=next_version, approved_revision=None, updated_at=utcnow())
    # Every save invalidates approval, including changes to title/visibility.
    values["status"] = values.get("status", "draft" if row.status in {"approved", "published"} else row.status)
    result = db.execute(update(Writeup).where(
        Writeup.id == row.id, Writeup.version == expected_version,
        Writeup.deleted_at.is_(None)
    ).values(**values).execution_options(synchronize_session=False))
    if result.rowcount != 1:
        db.rollback()
        current = db.get(Writeup, row.id)
        raise HTTPException(409, {"message": "Documento alterado por outra sessão",
                                  "current_version": current.version if current else None})
    db.add(WriteupRevision(writeup_id=row.id, version=next_version, title=title,
                          document=document, author_id=actor.id, message=message))
    db.execute(update(ReviewRequest).where(
        ReviewRequest.writeup_id == row.id, ReviewRequest.status.in_(["pending", "approved"])
    ).values(status="stale"))
    audit(db, actor, "writeup.saved", "writeup", row.id, {"version": next_version})
    db.commit()
    db.expire_all()
    return db.get(Writeup, row.id)


def revision_diff(first, second):
    def lines(revision):
        output = [f"# {revision.title}\n"]
        for section in revision.document["sections"]:
            output += [f"## {section['title']}\n", section["markdown"] + "\n"]
        return "".join(output).splitlines(keepends=True)
    return "".join(difflib.unified_diff(lines(first), lines(second),
                                       fromfile=f"v{first.version}", tofile=f"v{second.version}"))
