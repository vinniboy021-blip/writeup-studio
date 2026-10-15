# SPDX-License-Identifier: MIT
"""Storage privado, objetos imutáveis e respostas sem exposição de URLs S3."""
from __future__ import annotations

import io
import os
import re
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Iterator
from urllib.parse import quote

from fastapi import HTTPException
from fastapi.responses import FileResponse, StreamingResponse

from app.config import settings

CHUNK_SIZE = 64 * 1024


def _safe_key(key: str) -> str:
    path = PurePosixPath(key)
    if not key or path.is_absolute() or ".." in path.parts or "\\" in key or any(ord(c) < 32 for c in key):
        raise ValueError("Chave de armazenamento inválida")
    return key


def _local_path(key: str) -> Path:
    base = Path(getattr(settings, "upload_dir", getattr(settings, "storage_path", "./data/uploads"))).resolve()
    target = (base / _safe_key(key)).resolve()
    if not target.is_relative_to(base):
        raise ValueError("Objeto fora do armazenamento")
    return target


@lru_cache(maxsize=8)
def _s3_client(endpoint: str, access: str, secret: str, region: str):
    import boto3
    from botocore.config import Config
    return boto3.client(
        "s3", endpoint_url=endpoint or None, aws_access_key_id=access or None,
        aws_secret_access_key=secret or None, region_name=region,
        config=Config(connect_timeout=5, read_timeout=30, retries={"max_attempts": 2},
                      s3={"addressing_style": "path"}),
    )


def get_client():
    return _s3_client(settings.s3_endpoint_url, settings.s3_access_key, settings.s3_secret_key, settings.s3_region)


def put_object(key: str, data: bytes | BinaryIO, mime: str) -> None:
    """Cria objeto novo; chamadas nunca substituem originais ou derivados."""
    _safe_key(key)
    source = io.BytesIO(data) if isinstance(data, bytes) else data
    source.seek(0)
    if settings.storage_backend == "s3":
        from botocore.exceptions import ClientError
        try:
            get_client().put_object(Bucket=settings.s3_bucket, Key=key, Body=source,
                                    ContentType=mime, IfNoneMatch="*")
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in {"PreconditionFailed", "ConditionalRequestConflict", "412", "409"}:
                raise FileExistsError(key) from exc
            raise
        return
    target = _local_path(key)
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with target.open("xb") as destination:
            os.chmod(target, 0o600)
            while chunk := source.read(CHUNK_SIZE):
                destination.write(chunk)
    except FileExistsError:
        raise
    except Exception:
        target.unlink(missing_ok=True)
        raise


def iter_object(key: str) -> Iterator[bytes]:
    _safe_key(key)
    if settings.storage_backend == "s3":
        body = get_client().get_object(Bucket=settings.s3_bucket, Key=key)["Body"]
        try:
            yield from body.iter_chunks(CHUNK_SIZE)
        finally:
            body.close()
    else:
        with _local_path(key).open("rb") as source:
            while chunk := source.read(CHUNK_SIZE):
                yield chunk


def read_object(key: str, max_bytes: int = 32 * 1024 * 1024) -> bytes:
    parts = []
    size = 0
    for chunk in iter_object(key):
        size += len(chunk)
        if size > max_bytes:
            raise ValueError("Objeto acima do limite de leitura")
        parts.append(chunk)
    return b"".join(parts)


def delete_object(key: str) -> None:
    """Somente compensação de transação/retention; rota DELETE usa exclusão lógica."""
    _safe_key(key)
    if settings.storage_backend == "s3":
        get_client().delete_object(Bucket=settings.s3_bucket, Key=key)
    else:
        _local_path(key).unlink(missing_ok=True)


def object_response(key: str, mime: str, name: str, *, inline: bool = False):
    name = re.sub(r"[\x00-\x1f\x7f]", "", Path(name).name)[:240] or "evidence"
    headers = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
               "Content-Security-Policy": "default-src 'none'; sandbox"}
    disposition = "inline" if inline and mime in {"image/png", "image/jpeg", "image/webp"} else "attachment"
    if settings.storage_backend == "s3":
        headers["Content-Disposition"] = f"{disposition}; filename*=UTF-8''{quote(name, safe='')}"
        return StreamingResponse(iter_object(key), media_type=mime, headers=headers)
    path = _local_path(key)
    if not path.is_file():
        raise HTTPException(404, "Objeto não encontrado")
    return FileResponse(path, media_type=mime, filename=name, content_disposition_type=disposition, headers=headers)


def check_storage() -> None:
    if settings.storage_backend == "s3":
        get_client().head_bucket(Bucket=settings.s3_bucket)
    else:
        root = _local_path(".readiness").parent
        root.mkdir(parents=True, exist_ok=True)
        if not os.access(root, os.R_OK | os.W_OK):
            raise RuntimeError("Armazenamento sem acesso")
