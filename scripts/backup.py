#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""PostgreSQL + private objects backup, integrity checking and explicit restore."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from urllib.parse import parse_qs, unquote, urlsplit

CHUNK = 1024 * 1024


def pg_environment(database_url: str) -> dict[str, str]:
    parsed = urlsplit(database_url.replace("postgresql+psycopg://", "postgresql://", 1))
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise ValueError("Backup/restore exige PostgreSQL")
    query = parse_qs(parsed.query)
    database = unquote(parsed.path.lstrip("/"))
    if not database:
        raise ValueError("DATABASE_URL deve identificar um banco")
    result = dict(os.environ)
    result["PGDATABASE"] = database
    result["PGHOST"] = unquote(parsed.hostname or query.get("host", ["localhost"])[0])
    result["PGPORT"] = str(parsed.port or query.get("port", [5432])[0])
    if parsed.username:
        result["PGUSER"] = unquote(parsed.username)
    if parsed.password:
        result["PGPASSWORD"] = unquote(parsed.password)
    if query.get("sslmode"):
        result["PGSSLMODE"] = query["sslmode"][0]
    return result


def run_pg(binary: str, arguments: list[str], environment: dict[str, str]) -> None:
    try:
        subprocess.run([binary, *arguments], check=True, env=environment,
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"{binary} falhou (código {exc.returncode}); nenhuma credencial foi registrada") from exc


def checksum(path: Path) -> tuple[str, int]:
    digest, size = hashlib.sha256(), 0
    with path.open("rb") as source:
        while chunk := source.read(CHUNK):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def safe_key(key: str) -> str:
    path = PurePosixPath(key)
    if not key or path.is_absolute() or ".." in path.parts or "\\" in key or any(ord(c) < 32 for c in key):
        raise ValueError("Chave de objeto inválida")
    return key


def safe_file(root: Path, name: str) -> Path:
    safe_key(name)
    candidate = root / name
    if candidate.is_symlink() or not candidate.resolve().is_relative_to(root.resolve()) or not candidate.is_file():
        raise ValueError("Arquivo de backup inexistente ou fora do diretório")
    return candidate


def s3_client():
    import boto3
    from botocore.config import Config
    return boto3.client(
        "s3", endpoint_url=os.environ.get("S3_ENDPOINT_URL") or None,
        aws_access_key_id=os.environ.get("S3_ACCESS_KEY") or None,
        aws_secret_access_key=os.environ.get("S3_SECRET_KEY") or None,
        region_name=os.environ.get("S3_REGION", "us-east-1"),
        config=Config(connect_timeout=5, read_timeout=60, retries={"max_attempts": 2},
                      s3={"addressing_style": "path"}),
    )


def snapshot_references(connection) -> list[dict]:
    references = []
    for table in ("evidences", "evidence_versions"):
        if connection.execute("SELECT to_regclass(%s)", (table,)).fetchone()[0]:
            for key, digest in connection.execute(f"SELECT storage_key, sha256 FROM {table}"):
                if key:
                    references.append({"key": safe_key(key), "sha256": digest})
    if connection.execute("SELECT to_regclass('exports')").fetchone()[0]:
        for key, options in connection.execute("SELECT storage_key, options FROM exports WHERE status='completed'"):
            if key:
                references.append({"key": safe_key(key), "sha256": options.get("sha256")})
    return references


def backup(output: Path, retention_days: int = 30) -> Path:
    import psycopg
    database_url = os.environ.get("DATABASE_URL", "")
    environment = pg_environment(database_url)
    output.mkdir(mode=0o700, parents=True, exist_ok=True)
    if output.is_symlink():
        raise ValueError("Destino de backup não pode ser um link")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = output / f"backup-{stamp}-{uuid.uuid4().hex[:8]}"
    destination.mkdir(mode=0o700)
    (destination / "objects").mkdir(mode=0o700)
    with psycopg.connect(database_url.replace("postgresql+psycopg://", "postgresql://", 1)) as connection:
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        snapshot = connection.execute("SELECT pg_export_snapshot()").fetchone()[0]
        references = snapshot_references(connection)
        run_pg("pg_dump", ["--format=custom", "--no-owner", "--no-acl", "--snapshot", snapshot,
                           "--file", str(destination / "postgres.dump")], environment)
        backend = os.environ.get("STORAGE_BACKEND", "local")
        objects = []
        if backend == "s3":
            client, bucket = s3_client(), os.environ["S3_BUCKET"]
            for page in client.get_paginator("list_objects_v2").paginate(Bucket=bucket):
                for entry in page.get("Contents", []):
                    key = safe_key(entry["Key"])
                    target = destination / "objects" / str(len(objects))
                    response = client.get_object(Bucket=bucket, Key=key)
                    try:
                        with target.open("xb") as stream:
                            for chunk in response["Body"].iter_chunks(CHUNK):
                                stream.write(chunk)
                    finally:
                        response["Body"].close()
                    digest, size = checksum(target)
                    objects.append({"key": key, "file": str(target.relative_to(destination)),
                                    "sha256": digest, "size": size,
                                    "content_type": response.get("ContentType", "application/octet-stream")})
        elif backend == "local":
            source = Path(os.environ.get("UPLOAD_DIR", "./data/uploads"))
            if source.exists():
                for path in sorted(source.rglob("*")):
                    if path.is_symlink():
                        raise ValueError("Storage contém links simbólicos; backup recusado")
                    if not path.is_file():
                        continue
                    key = safe_key(path.relative_to(source).as_posix())
                    target = destination / "objects" / str(len(objects))
                    shutil.copyfile(path, target)
                    digest, size = checksum(target)
                    objects.append({"key": key, "file": str(target.relative_to(destination)),
                                    "sha256": digest, "size": size, "content_type": "application/octet-stream"})
        else:
            raise ValueError("STORAGE_BACKEND inválido")
    digest, size = checksum(destination / "postgres.dump")
    manifest = {"schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
                "storage_backend": backend, "database": {"file": "postgres.dump", "sha256": digest, "size": size},
                "objects": objects, "references": references}
    with (destination / "manifest.json").open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
    for path in destination.rglob("*"):
        if path.is_file():
            path.chmod(0o600)
    verify(destination)
    # Only complete, verified backups created by this tool are subject to retention.
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    for previous in output.glob("backup-*"):
        if previous == destination or previous.is_symlink() or not previous.is_dir():
            continue
        try:
            prior = verify(previous)
            if datetime.fromisoformat(prior["created_at"]) < cutoff:
                shutil.rmtree(previous)
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            continue
    return destination


def verify(directory: Path) -> dict:
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("Diretório de backup inválido")
    manifest_path = safe_file(directory, "manifest.json")
    if manifest_path.stat().st_size > 64 * 1024 * 1024:
        raise ValueError("Manifesto excede limite")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1:
        raise ValueError("Schema de backup não suportado")
    seen_files, seen_keys = set(), set()
    for entry in [manifest["database"], *manifest["objects"]]:
        name = entry["file"]
        if name in seen_files or name == "manifest.json":
            raise ValueError("Manifesto contém arquivos duplicados")
        seen_files.add(name)
        digest, size = checksum(safe_file(directory, name))
        if digest != entry["sha256"] or size != entry["size"]:
            raise ValueError("Falha de integridade SHA-256/tamanho")
        if "key" in entry:
            key = safe_key(entry["key"])
            if key in seen_keys:
                raise ValueError("Manifesto contém chaves duplicadas")
            seen_keys.add(key)
    available = {entry["key"]: entry["sha256"] for entry in manifest["objects"]}
    for reference in manifest.get("references", []):
        if reference["key"] not in available or (reference.get("sha256") and
                                                 reference["sha256"] != available[reference["key"]]):
            raise ValueError("Objeto referenciado pelo snapshot ausente ou alterado")
    return manifest


def restore(directory: Path, database_url: str, confirm_database: str, replace_objects: bool = False) -> None:
    environment = pg_environment(database_url)
    if confirm_database != environment["PGDATABASE"]:
        raise ValueError("--confirm-replace deve ser exatamente o nome do banco de destino")
    manifest = verify(directory)
    backend = os.environ.get("STORAGE_BACKEND", "local")
    # Preflight every object before touching the target database; immutable objects may coexist.
    if backend == "local":
        target_root = Path(os.environ.get("UPLOAD_DIR", "./data/uploads")).resolve()
        if target_root == Path("/") or target_root.is_symlink():
            raise ValueError("Storage de destino inválido")
        for entry in manifest["objects"]:
            target = target_root / safe_key(entry["key"])
            if not target.resolve().is_relative_to(target_root):
                raise ValueError("Destino de objeto fora do storage")
            if target.exists() and checksum(target)[0] != entry["sha256"] and not replace_objects:
                raise ValueError("Objeto diferente já existe; use storage vazio ou --replace-objects explícito")
        for entry in manifest["objects"]:
            target = target_root / entry["key"]
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists() or checksum(target)[0] != entry["sha256"]:
                shutil.copyfile(safe_file(directory, entry["file"]), target)
                target.chmod(0o600)
    elif backend == "s3":
        from botocore.exceptions import ClientError
        client, bucket = s3_client(), os.environ["S3_BUCKET"]
        pending = []
        for entry in manifest["objects"]:
            try:
                body = client.get_object(Bucket=bucket, Key=entry["key"])["Body"]
                digest = hashlib.sha256()
                try:
                    for chunk in body.iter_chunks(CHUNK):
                        digest.update(chunk)
                finally:
                    body.close()
                if digest.hexdigest() == entry["sha256"]:
                    continue
                if not replace_objects:
                    raise ValueError("Objeto S3 diferente já existe; restaure em bucket vazio")
            except ClientError as exc:
                if exc.response.get("Error", {}).get("Code") not in {"NoSuchKey", "404"}:
                    raise
            pending.append(entry)
        for entry in pending:
            with safe_file(directory, entry["file"]).open("rb") as body:
                args = {} if replace_objects else {"IfNoneMatch": "*"}
                client.put_object(Bucket=bucket, Key=entry["key"], Body=body,
                                  ContentType=entry["content_type"], **args)
    else:
        raise ValueError("STORAGE_BACKEND inválido")
    run_pg("pg_restore", ["--clean", "--if-exists", "--no-owner", "--no-acl", "--exit-on-error",
                           "--single-transaction", "--dbname", environment["PGDATABASE"],
                           str(safe_file(directory, manifest["database"]["file"]))], environment)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Backup e restauração PostgreSQL + evidências")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("backup")
    create.add_argument("--output", type=Path, default=Path("backups"))
    create.add_argument("--retention-days", type=int, default=int(os.environ.get("BACKUP_RETENTION_DAYS", "30")))
    check = commands.add_parser("verify")
    check.add_argument("directory", type=Path)
    recover = commands.add_parser("restore")
    recover.add_argument("directory", type=Path)
    recover.add_argument("--confirm-replace", required=True, help="Nome exato do banco que será substituído")
    recover.add_argument("--replace-objects", action="store_true", help="Permitir substituir objetos diferentes")
    args = parser.parse_args(argv)
    try:
        if args.command == "backup":
            if args.retention_days < 1:
                raise ValueError("Retenção mínima de um dia")
            path = backup(args.output, args.retention_days)
            print(f"Backup completo e verificado: {path.name}")
        elif args.command == "verify":
            manifest = verify(args.directory)
            print(f"Integridade verificada: banco e {len(manifest['objects'])} objetos")
        else:
            restore(args.directory, os.environ.get("DATABASE_URL", ""), args.confirm_replace, args.replace_objects)
            print("Banco e objetos restaurados; valide login, documentos e downloads antes de reabrir o serviço.")
        return 0
    except Exception as exc:
        # SDK/database errors may embed credentials: expose only exception type for operational logs.
        message = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
        print(f"Operação não concluída: {message}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
