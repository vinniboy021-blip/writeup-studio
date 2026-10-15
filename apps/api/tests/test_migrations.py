import os
import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from app.db import make_engine
from app.models import Base

API_DIR = Path(__file__).resolve().parents[1]


def migration_config(url):
    config = Config(str(API_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(API_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", url)
    return config


def test_sqlite_real_migrations_upgrade_downgrade_and_constraints(tmp_path):
    url = "sqlite:///" + str(tmp_path / "migration.db")
    config = migration_config(url)
    command.upgrade(config, "head")
    engine = make_engine(url)
    assert set(Base.metadata.tables).issubset(inspect(engine).get_table_names())
    assert inspect(engine).get_unique_constraints("writeup_revisions")
    with engine.connect() as db:
        assert db.scalar(text("SELECT version_num FROM alembic_version")) == "0004"
        assert db.exec_driver_sql("PRAGMA foreign_key_check").fetchall() == []
    engine.dispose()
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    assert "evidence_versions" in inspect(make_engine(url)).get_table_names()


def test_legacy_adoption_preserves_documents_originals_and_reverses_schema(tmp_path):
    url = "sqlite:///" + str(tmp_path / "legacy.db")
    engine = make_engine(url)
    owner, team, writeup, evidence = [str(uuid4()) for _ in range(4)]
    document = {"schema_version": 1, "sections": [{"id": "s1", "title": "Observed", "markdown": "Original notes"}]}
    with engine.begin() as db:
        db.exec_driver_sql(
            "CREATE TABLE users (id VARCHAR(36) PRIMARY KEY, email VARCHAR(320) NOT NULL UNIQUE, name VARCHAR(160) NOT NULL, password_hash VARCHAR(255) NOT NULL, is_admin BOOLEAN NOT NULL, created_at DATETIME NOT NULL)"
        )
        db.execute(
            text(
                "INSERT INTO users VALUES (:id,'legacy@example.org','Legacy','pbkdf2$legacy',0,'2026-01-01 00:00:00')"
            ),
            {"id": owner},
        )
        db.exec_driver_sql(
            "CREATE TABLE teams (id VARCHAR(36) PRIMARY KEY, name VARCHAR(160) NOT NULL, owner_id VARCHAR(36) NOT NULL REFERENCES users(id), created_at DATETIME NOT NULL)"
        )
        db.execute(
            text("INSERT INTO teams VALUES (:id,'Legacy team',:owner,'2026-01-01 00:00:00')"),
            {"id": team, "owner": owner},
        )
        db.exec_driver_sql(
            "CREATE TABLE team_members (id INTEGER PRIMARY KEY, team_id VARCHAR(36) NOT NULL REFERENCES teams(id), user_id VARCHAR(36) NOT NULL REFERENCES users(id), role VARCHAR(30) NOT NULL)"
        )
        db.execute(text("INSERT INTO team_members VALUES (1,:team,:owner,'manager')"), {"team": team, "owner": owner})
        db.exec_driver_sql(
            "CREATE TABLE writeups (id VARCHAR(36) PRIMARY KEY, owner_id VARCHAR(36) NOT NULL REFERENCES users(id), challenge_id VARCHAR(36), team_id VARCHAR(36), title VARCHAR(240) NOT NULL, document JSON NOT NULL, status VARCHAR(30) NOT NULL, visibility VARCHAR(20) NOT NULL, version INTEGER NOT NULL, updated_at DATETIME NOT NULL)"
        )
        db.execute(
            text(
                "INSERT INTO writeups VALUES (:id,:owner,NULL,NULL,'Original writeup',:document,'approved','public',1,'2026-01-01 00:00:00')"
            ),
            {"id": writeup, "owner": owner, "document": json.dumps(document)},
        )
        db.exec_driver_sql(
            "CREATE TABLE evidences (id VARCHAR(36) PRIMARY KEY, owner_id VARCHAR(36) NOT NULL REFERENCES users(id), name VARCHAR(240) NOT NULL, description TEXT NOT NULL, origin VARCHAR(500) NOT NULL, sha256 VARCHAR(64) NOT NULL, size INTEGER NOT NULL, mime_type VARCHAR(120) NOT NULL, storage_key VARCHAR(500) NOT NULL, visibility VARCHAR(20) NOT NULL, created_at DATETIME NOT NULL)"
        )
        db.execute(
            text(
                "INSERT INTO evidences VALUES (:id,:owner,'Original.txt','','capture',:sha,5,'text/plain','original-key','private','2026-01-01 00:00:00')"
            ),
            {"id": evidence, "owner": owner, "sha": "a" * 64},
        )
    engine.dispose()
    config = migration_config(url)
    command.upgrade(config, "head")
    engine = make_engine(url)
    with engine.connect() as db:
        row = db.execute(
            text("SELECT title,document,status,visibility FROM writeups WHERE id=:id"), {"id": writeup}
        ).one()
        assert row.title == "Original writeup" and json.loads(row.document) == document
        assert row.status == "draft" and row.visibility == "private"
        assert db.scalar(text("SELECT storage_key FROM evidences WHERE id=:id"), {"id": evidence}) == "original-key"
        UUID(db.scalar(text("SELECT id FROM team_members")))
        assert db.exec_driver_sql("PRAGMA foreign_key_check").fetchall() == []
    engine.dispose()
    command.downgrade(config, "0001")
    engine = make_engine(url)
    assert "is_active" not in {column["name"] for column in inspect(engine).get_columns("users")}
    with engine.connect() as db:
        assert db.scalar(text("SELECT id FROM team_members")) == 1
        assert db.scalar(text("SELECT visibility FROM writeups WHERE id=:id"), {"id": writeup}) == "public"


@pytest.mark.postgres
def test_postgresql_migrations_are_reversible():
    url = os.getenv("TEST_DATABASE_URL", "")
    if not url:
        pytest.skip("TEST_DATABASE_URL PostgreSQL não configurada")
    assert url.startswith("postgresql")
    config = migration_config(url)
    command.upgrade(config, "head")
    engine = make_engine(url)
    assert set(Base.metadata.tables).issubset(inspect(engine).get_table_names())
    engine.dispose()
    command.downgrade(config, "base")
    command.upgrade(config, "head")
