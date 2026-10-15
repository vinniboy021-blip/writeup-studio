# SPDX-License-Identifier: MIT
import hashlib
import importlib.util
import json
import os
import shutil
from pathlib import Path
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("studio_backup", ROOT / "scripts/backup.py")
backup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup)


def fixture_backup(path):
    path.mkdir()
    (path / "objects").mkdir()
    (path / "postgres.dump").write_bytes(b"example dump fixture")
    (path / "objects/0").write_bytes(b"authentic evidence fixture")
    digest, size = backup.checksum(path / "postgres.dump")
    obj_digest, obj_size = backup.checksum(path / "objects/0")
    manifest = {"schema_version": 1, "created_at": "2026-10-14T00:00:00+00:00",
                "database": {"file": "postgres.dump", "sha256": digest, "size": size},
                "objects": [{"file": "objects/0", "key": "evidences/original.txt",
                             "sha256": obj_digest, "size": obj_size, "content_type": "text/plain"}],
                "references": [{"key": "evidences/original.txt", "sha256": obj_digest}]}
    (path / "manifest.json").write_text(json.dumps(manifest))
    return manifest


def test_integrity_detects_corruption_and_invalid_reference(tmp_path):
    path = tmp_path / "snapshot"
    manifest = fixture_backup(path)
    assert backup.verify(path)["schema_version"] == 1
    (path / "objects/0").write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="integridade"):
        backup.verify(path)
    (path / "objects/0").write_bytes(b"authentic evidence fixture")
    manifest["references"][0]["sha256"] = "0" * 64
    (path / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="referenciado"):
        backup.verify(path)


def test_integrity_rejects_traversal_symlinks_and_duplicate_objects(tmp_path):
    path = tmp_path / "snapshot"
    manifest = fixture_backup(path)
    manifest["objects"][0]["file"] = "../outside"
    (path / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        backup.verify(path)
    manifest["objects"][0]["file"] = "objects/0"
    (path / "objects/0").unlink()
    (tmp_path / "outside").write_bytes(b"authentic evidence fixture")
    (path / "objects/0").symlink_to(tmp_path / "outside")
    (path / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        backup.verify(path)


def test_restore_requires_exact_database_target_before_any_mutation(tmp_path, monkeypatch):
    path = tmp_path / "snapshot"
    fixture_backup(path)
    with pytest.raises(ValueError, match="confirm-replace"):
        backup.restore(path, "postgresql://localhost/disposable", "production")
    environment = backup.pg_environment("postgresql+psycopg://user:secret@localhost:6543/disposable?sslmode=require")
    assert environment["PGPASSWORD"] == "secret" and environment["PGPORT"] == "6543"
    assert environment["PGSSLMODE"] == "require"
    with pytest.raises(ValueError):
        backup.pg_environment("sqlite:///data.db")


@pytest.fixture
def postgres_pair(monkeypatch):
    import psycopg
    from psycopg import sql
    from psycopg.conninfo import conninfo_to_dict, make_conninfo
    admin_url = os.getenv("TEST_BACKUP_PG_ADMIN_URL")
    if not admin_url or not shutil.which("pg_dump") or not shutil.which("pg_restore"):
        pytest.skip("PostgreSQL administrativo/pg_dump/pg_restore não configurados")
    suffix = uuid4().hex[:16]
    source, target = f"backup_src_{suffix}", f"backup_dst_{suffix}"
    with psycopg.connect(admin_url, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(source)))
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(target)))
    parameters = conninfo_to_dict(admin_url)
    try:
        yield make_conninfo(**{**parameters, "dbname": source}), make_conninfo(**{**parameters, "dbname": target})
    finally:
        with psycopg.connect(admin_url, autocommit=True) as connection:
            for name in (source, target):
                connection.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


def connection_url(conninfo):
    from psycopg.conninfo import conninfo_to_dict
    from urllib.parse import quote
    values = conninfo_to_dict(conninfo)
    username = quote(values.get("user", "postgres"), safe="")
    password = ":" + quote(values["password"], safe="") if values.get("password") else ""
    host = values.get("host", "localhost")
    if host.startswith("/"):
        return f"postgresql://{username}{password}@/{values['dbname']}?host={quote(host, safe='')}&port={values.get('port', '5432')}"
    return f"postgresql://{username}{password}@{host}:{values.get('port', '5432')}/{values['dbname']}"


@pytest.mark.parametrize("backend", ["local", "s3"])
def test_real_postgres_and_objects_restore_roundtrip(postgres_pair, tmp_path, monkeypatch, backend):
    import psycopg
    from moto import mock_aws
    source, target = postgres_pair
    content = b"immutable authentic captured test bytes\n"
    digest = hashlib.sha256(content).hexdigest()
    with psycopg.connect(source) as connection:
        connection.execute("CREATE TABLE evidences (storage_key TEXT PRIMARY KEY, sha256 TEXT NOT NULL)")
        connection.execute("INSERT INTO evidences VALUES (%s,%s)", ("original/capture.txt", digest))
    monkeypatch.setenv("DATABASE_URL", connection_url(source))
    monkeypatch.setenv("STORAGE_BACKEND", backend)
    if backend == "local":
        storage = tmp_path / "source-objects/original"
        storage.mkdir(parents=True)
        (storage / "capture.txt").write_bytes(content)
        monkeypatch.setenv("UPLOAD_DIR", str(storage.parent))
        snapshot = backup.backup(tmp_path / "backups")
        monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "target-objects"))
        backup.restore(snapshot, connection_url(target), connection_url(target).split("/")[3].split("?")[0])
        assert (tmp_path / "target-objects/original/capture.txt").read_bytes() == content
    else:
        monkeypatch.setenv("S3_BUCKET", "source-evidences")
        monkeypatch.setenv("S3_ACCESS_KEY", "testing")
        monkeypatch.setenv("S3_SECRET_KEY", "testing")
        monkeypatch.setenv("S3_ENDPOINT_URL", "")
        with mock_aws():
            client = backup.s3_client()
            client.create_bucket(Bucket="source-evidences")
            client.put_object(Bucket="source-evidences", Key="original/capture.txt", Body=content, ContentType="text/plain")
            snapshot = backup.backup(tmp_path / "backups")
            client.create_bucket(Bucket="target-evidences")
            monkeypatch.setenv("S3_BUCKET", "target-evidences")
            backup.restore(snapshot, connection_url(target), connection_url(target).split("/")[3].split("?")[0])
            assert client.get_object(Bucket="target-evidences", Key="original/capture.txt")["Body"].read() == content
    with psycopg.connect(target) as connection:
        assert connection.execute("SELECT sha256 FROM evidences").fetchone()[0] == digest
    assert backup.verify(snapshot)["references"][0]["sha256"] == digest
