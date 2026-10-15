# SPDX-License-Identifier: MIT
"""Validação pelo conteúdo; extensões e MIME do cliente não são autoridade."""
from __future__ import annotations

import csv
import io
import json
import warnings
import zipfile
from pathlib import Path, PurePosixPath
from typing import BinaryIO

import magic
from fastapi import HTTPException
from PIL import Image, UnidentifiedImageError

from app.config import settings

Image.MAX_IMAGE_PIXELS = 24_000_000
EXTENSIONS = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".webp": "image/webp", ".gif": "image/gif", ".txt": "text/plain",
    ".log": "text/plain", ".json": "application/json", ".csv": "text/csv",
    ".pcap": "application/vnd.tcpdump.pcap", ".pcapng": "application/x-pcapng",
    ".pdf": "application/pdf", ".zip": "application/zip",
}
FORMATS = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp", "GIF": "image/gif"}


def validate_image(source: BinaryIO) -> tuple[str, dict]:
    source.seek(0)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(source) as image:
                mime = FORMATS.get(image.format)
                if not mime:
                    raise ValueError("Formato de imagem não permitido")
                if image.width * image.height > Image.MAX_IMAGE_PIXELS:
                    raise ValueError("Imagem excede limite de 24 megapixels")
                metadata = {"width": image.width, "height": image.height,
                            "frames": getattr(image, "n_frames", 1)}
                if metadata["frames"] > 100:
                    raise ValueError("GIF acima do limite de quadros")
                image.verify()
            source.seek(0)
            # Decodifica o primeiro quadro em vez de confiar somente no cabeçalho.
            with Image.open(source) as image:
                image.seek(0)
                image.load()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise HTTPException(422, "Imagem inválida ou acima dos limites") from exc
    finally:
        source.seek(0)
    return mime, metadata


def _validate_zip(source: BinaryIO) -> dict:
    if not getattr(settings, "allow_archives", False):
        raise HTTPException(422, "Arquivos compactados estão desabilitados pela política")
    try:
        source.seek(0)
        with zipfile.ZipFile(source) as archive:
            members = archive.infolist()
            if len(members) > 500:
                raise ValueError("Muitas entradas")
            expanded = 0
            for member in members:
                path = PurePosixPath(member.filename)
                if path.is_absolute() or ".." in path.parts or "\\" in member.filename or member.flag_bits & 1:
                    raise ValueError("Caminho ou criptografia não permitidos")
                if (member.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError("Link simbólico não permitido")
                expanded += member.file_size
                if member.file_size > 50 * 1024 * 1024 or member.file_size / max(member.compress_size, 1) > 100:
                    raise ValueError("Limite de expansão")
            if expanded > 100 * 1024 * 1024:
                raise ValueError("Limite de expansão")
            # Nunca extrai entradas; originais ficam opacos no armazenamento privado.
            return {"archive_entries": len(members), "declared_uncompressed_size": expanded}
    except (zipfile.BadZipFile, ValueError) as exc:
        raise HTTPException(422, "Arquivo ZIP inválido ou proibido pela política") from exc
    finally:
        source.seek(0)


def validate_file(source: BinaryIO, filename: str, declared_mime: str | None) -> tuple[str, str, dict]:
    extension = Path(filename).suffix.lower()
    expected = EXTENSIONS.get(extension)
    if not expected:
        raise HTTPException(422, "Extensão não permitida")
    source.seek(0)
    sample = source.read(65536)
    source.seek(0)
    if not sample:
        raise HTTPException(422, "Arquivo vazio")
    detected = magic.from_buffer(sample, mime=True)
    metadata = {}
    if expected.startswith("image/"):
        actual, metadata = validate_image(source)
        if actual != expected:
            raise HTTPException(422, "Extensão não corresponde ao conteúdo real da imagem")
    elif expected in {"text/plain", "text/csv", "application/json"}:
        try:
            data = source.read(settings.max_upload_bytes + 1)
            if len(data) > settings.max_upload_bytes:
                raise ValueError("Arquivo acima do limite")
            text = data.decode("utf-8-sig")
            if "\x00" in text or any(ord(c) < 9 or 13 < ord(c) < 32 for c in text):
                raise ValueError("Conteúdo binário")
            if expected == "application/json":
                json.loads(text, parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Número não finito")))
            elif expected == "text/csv":
                # A validação de CSV não infere nem executa fórmulas.
                rows = csv.reader(io.StringIO(text))
                for index, row in enumerate(rows):
                    if len(row) > 1000:
                        raise ValueError("CSV com muitas colunas")
                    if index >= 10000:
                        break
            metadata = {"encoding": "utf-8"}
        except (UnicodeDecodeError, ValueError, RecursionError, csv.Error) as exc:
            raise HTTPException(422, "Conteúdo textual inválido para a extensão") from exc
        finally:
            source.seek(0)
    elif expected == "application/pdf":
        if not sample.startswith(b"%PDF-"):
            raise HTTPException(422, "Cabeçalho PDF inválido")
        source.seek(0, 2)
        length = source.tell()
        source.seek(max(0, length - 4096))
        if b"%%EOF" not in source.read():
            raise HTTPException(422, "PDF truncado")
        source.seek(0)
        metadata = {"active_content": "not_rendered", "download_only": True}
    elif expected == "application/vnd.tcpdump.pcap":
        if len(sample) < 24 or sample[:4] not in {b"\xd4\xc3\xb2\xa1", b"\xa1\xb2\xc3\xd4", b"\x4d\x3c\xb2\xa1", b"\xa1\xb2\x3c\x4d"}:
            raise HTTPException(422, "Cabeçalho PCAP inválido")
        metadata = {"download_only": True}
    elif expected == "application/x-pcapng":
        if len(sample) < 28 or sample[:4] != b"\x0a\x0d\x0d\x0a" or sample[8:12] not in {b"\x1a\x2b\x3c\x4d", b"\x4d\x3c\x2b\x1a"}:
            raise HTTPException(422, "Cabeçalho PCAPNG inválido")
        metadata = {"download_only": True}
    elif expected == "application/zip":
        metadata = _validate_zip(source)
    declared = (declared_mime or "application/octet-stream").split(";", 1)[0].strip().lower()
    aliases = {"image/jpg": "image/jpeg", "application/x-zip-compressed": "application/zip",
               "application/x-pcap": "application/vnd.tcpdump.pcap", "text/json": "application/json"}
    if aliases.get(declared, declared) not in {expected, "application/octet-stream"}:
        raise HTTPException(422, "MIME declarado não corresponde ao conteúdo validado")
    metadata["detected_mime"] = detected
    if expected == "image/gif":
        metadata["preview_policy"] = "static_first_frame"
    return expected, extension, metadata
