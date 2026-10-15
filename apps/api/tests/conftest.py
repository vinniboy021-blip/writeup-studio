"""Real migrated isolated database fixtures; never use create_all."""

import os
from pathlib import Path

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.db import get_db, make_engine
from app.security import _attempts

API_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture
def engine(tmp_path):
    database_url = "sqlite:///" + str(tmp_path / "test.db")
    config = Config(str(API_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(API_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")
    result = make_engine(database_url)
    yield result
    result.dispose()


@pytest.fixture
def db(engine):
    with sessionmaker(engine, expire_on_commit=False)() as session:
        yield session
        session.rollback()


@pytest.fixture
def client(engine, tmp_path, monkeypatch):
    from app.main import app
    from app.modules.workspace.services import seed_workspace

    sessions = sessionmaker(engine, expire_on_commit=False, autoflush=False)
    with sessions() as session:
        seed_workspace(session)

    def override_db():
        with sessions() as session:
            try:
                yield session
            except Exception:
                session.rollback()
                raise

    monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "objects"))
    monkeypatch.setattr(settings, "storage_backend", "local")
    monkeypatch.setattr(settings, "queue_enabled", False)
    monkeypatch.setattr(settings, "rate_limit_backend", "memory")
    _attempts.clear()
    app.dependency_overrides[get_db] = override_db
    with TestClient(app, raise_server_exceptions=True) as result:
        yield result
    app.dependency_overrides.clear()


@pytest.fixture
def auth_factory(client):
    def register(email="owner@example.org", name="Owner", password="Strong-password-123!"):
        response = client.post("/api/v1/auth/register", json={"email": email, "name": name, "password": password})
        assert response.status_code == 201, response.text
        data = response.json()
        return {
            **data,
            "headers": {"X-CSRF-Token": data["csrf_token"]},
            "client": client,
            "cookies": dict(client.cookies),
            "password": password,
        }

    return register


@pytest.fixture
def auth(auth_factory):
    return auth_factory()
