# SPDX-License-Identifier: MIT
"""Optional real PostgreSQL/Redis checks, isolated from application data."""

import os
from pathlib import Path
import uuid

from alembic import command
from alembic.config import Config
from fastapi import HTTPException
import pytest
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.db import make_engine
from app.models import User, Writeup, WriteupRevision
from app.modules.studio import jobs
from app.modules.studio.services import save_revision
from app.modules.workspace.schemas import CompetitionCreate
from app.modules.workspace.services import create_competition, search


@pytest.fixture
def postgres_engine():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL required for real PostgreSQL")
    admin = make_engine(url)
    schema = "ctf_test_" + uuid.uuid4().hex
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    parsed = make_url(url).update_query_dict({"options": "-csearch_path=" + schema})
    scoped_url = parsed.render_as_string(hide_password=False)
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "alembic"))
    config.set_main_option("sqlalchemy.url", scoped_url.replace("%", "%%"))
    command.upgrade(config, "head")
    engine = make_engine(scoped_url)
    try:
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


@pytest.mark.postgres
def test_real_postgresql_search_content_is_paginated_and_private(postgres_engine):
    with Session(postgres_engine, expire_on_commit=False) as db:
        owner = User(email="postgres-owner@example.org", name="Owner", password_hash="fixture-only", is_active=True)
        outsider = User(email="postgres-other@example.org", name="Other", password_hash="fixture-only", is_active=True)
        db.add_all([owner, outsider])
        db.commit()
        created = create_competition(
            db, owner, CompetitionCreate(name="Análise de evidências", description="segredo forense exclusivo")
        )
        found = search(db, owner, q="forense", page=1, page_size=1)
        assert found["total"] == 1
        assert found["items"][0]["id"] == created["id"]
        assert search(db, outsider, q="forense")["total"] == 0
        assert search(db, owner, q="forense", page=2, page_size=1)["items"] == []


@pytest.mark.postgres
def test_real_postgresql_two_sessions_cas_preserves_only_winning_revision(postgres_engine):
    factory = sessionmaker(postgres_engine, expire_on_commit=False)
    with factory() as db:
        owner = User(email="cas-owner@example.org", name="Owner", password_hash="fixture-only", is_active=True)
        db.add(owner)
        db.flush()
        writeup = Writeup(owner_id=owner.id, title="Initial", document={"schema_version": 1, "sections": []})
        db.add(writeup)
        db.flush()
        db.add(
            WriteupRevision(
                writeup_id=writeup.id, author_id=owner.id, version=1, title=writeup.title, document=writeup.document
            )
        )
        db.commit()
        owner_id, writeup_id = owner.id, writeup.id
    with factory() as first, factory() as second:
        a, b = first.get(Writeup, writeup_id), second.get(Writeup, writeup_id)
        assert a.version == b.version == 1
        save_revision(first, first.get(User, owner_id), a, 1, {"title": "Winning revision"})
        with pytest.raises(HTTPException) as conflict:
            save_revision(second, second.get(User, owner_id), b, 1, {"title": "Lost revision"})
        assert conflict.value.status_code == 409
    with factory() as db:
        assert db.get(Writeup, writeup_id).title == "Winning revision"
        assert [
            r.version
            for r in db.scalars(
                select(WriteupRevision)
                .where(WriteupRevision.writeup_id == writeup_id)
                .order_by(WriteupRevision.version)
            )
        ] == [1, 2]


@pytest.mark.integration
def test_real_rq_worker_produces_pdf_and_updates_state(client, auth, engine, monkeypatch):
    url = os.getenv("TEST_REDIS_URL")
    if not url:
        pytest.skip("TEST_REDIS_URL required for real RQ integration")
    from redis import Redis
    from rq import Queue, SimpleWorker

    connection = Redis.from_url(url, socket_timeout=5)
    assert connection.ping()
    queue_name = "ctf-test-" + uuid.uuid4().hex
    monkeypatch.setattr(settings, "redis_url", url)
    monkeypatch.setattr(settings, "queue_name", queue_name)
    monkeypatch.setattr(settings, "queue_enabled", True)
    monkeypatch.setattr(settings, "queue_eager", False)
    monkeypatch.setattr(jobs, "SessionLocal", sessionmaker(engine, expire_on_commit=False))
    created = client.post(
        "/api/v1/writeups",
        json={
            "title": "Queued PDF",
            "document": {
                "schema_version": 1,
                "sections": [{"id": "observed", "title": "Observado", "markdown": "Test fixture data"}],
            },
        },
        headers=auth["headers"],
    )
    assert created.status_code == 201, created.text
    response = client.post(
        f"/api/v1/writeups/{created.json()['id']}/exports", json={"format": "pdf"}, headers=auth["headers"]
    )
    assert response.status_code == 202, response.text
    export_id = response.json()["id"]
    assert response.json()["status"] == "queued"
    queue = Queue(queue_name, connection=connection)
    try:
        SimpleWorker([queue], connection=connection).work(burst=True, with_scheduler=False)
        result = client.get(f"/api/v1/exports/{export_id}")
        assert result.json()["status"] == "completed", result.text
        downloaded = client.get(f"/api/v1/exports/{export_id}/download")
        assert downloaded.status_code == 200 and downloaded.content.startswith(b"%PDF-")
    finally:
        queue.delete(delete_jobs=True)
