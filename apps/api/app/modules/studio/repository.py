# SPDX-License-Identifier: MIT
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Writeup
from app.security import visible_query


def paginate(db: Session, statement, page: int, page_size: int, serializer):
    total = db.scalar(select(func.count()).select_from(statement.order_by(None).subquery())) or 0
    rows = db.scalars(statement.offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": [serializer(row) for row in rows], "total": total,
            "page": page, "page_size": page_size}


def visible_writeups(db, actor):
    return visible_query(select(Writeup).where(Writeup.deleted_at.is_(None)), Writeup, actor, db)
