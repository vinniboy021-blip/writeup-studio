# SPDX-License-Identifier: MIT
"""Consultas paginadas e atualização condicional compartilhadas pelo módulo."""

from fastapi import HTTPException
from sqlalchemy import func, select, update


def paginated(db, statement, page=1, page_size=25):
    total = db.scalar(select(func.count()).select_from(statement.order_by(None).subquery())) or 0
    rows = db.scalars(statement.offset((page - 1) * page_size).limit(page_size)).all()
    return rows, total


def atomic_update(db, model, resource_id, expected_version, values):
    result = db.execute(
        update(model)
        .where(model.id == resource_id, model.version == expected_version, model.deleted_at.is_(None))
        .values(**values, version=expected_version + 1)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "O recurso foi alterado. Recarregue antes de salvar.")
    db.expire_all()
    return db.get(model, resource_id)
