#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Generate private Compose settings without displaying secrets."""
from __future__ import annotations

import argparse
import os
import re
import secrets
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = ("POSTGRES_PASSWORD", "REDIS_PASSWORD", "MINIO_ROOT_PASSWORD", "S3_SECRET_KEY",
            "SECRET_KEY", "GRAFANA_ADMIN_PASSWORD", "KALI_MCP_TOKEN")


def read_env(path: Path) -> dict[str, str]:
    if path.is_symlink():
        raise ValueError("Arquivo de configuração não pode ser um link simbólico")
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator or not re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
            raise ValueError("Linha inválida no arquivo de configuração")
        values[key] = value.strip().strip("\"'")
    return values


def validate(values: dict[str, str], production: bool) -> None:
    for key in REQUIRED:
        value = values.get(key, "")
        if len(value) < 32 or value.lower().startswith(("change", "development", "example")):
            raise ValueError(f"{key}: segredo forte de pelo menos 32 caracteres obrigatório")
    parsed = urlsplit(values.get("PUBLIC_ORIGIN", ""))
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.path or parsed.query or parsed.fragment:
        raise ValueError("PUBLIC_ORIGIN precisa ser uma origem HTTP(S) sem caminho")
    if parsed.username or parsed.password:
        raise ValueError("PUBLIC_ORIGIN não pode conter credenciais")
    if not values.get("DATABASE_URL", "").startswith("postgresql+psycopg://"):
        raise ValueError("Configuração Compose requer PostgreSQL com psycopg")
    if values.get("STORAGE_BACKEND") != "s3" or not values.get("S3_BUCKET"):
        raise ValueError("Configuração Compose requer bucket S3 privado")
    if production and (parsed.scheme != "https" or values.get("COOKIE_SECURE") != "true"):
        raise ValueError("Produção requer HTTPS e COOKIE_SECURE=true")
    if values.get("QUEUE_ENABLED") != "true" or values.get("RATE_LIMIT_BACKEND") != "redis":
        raise ValueError("Compose requer fila e rate limiting Redis")


def generate(production: bool, origin: str) -> dict[str, str]:
    password = secrets.token_hex(32)
    values = {
        "ENVIRONMENT": "production" if production else "development",
        "PUBLIC_ORIGIN": origin, "APP_BIND": "0.0.0.0" if production else "127.0.0.1",
        "APP_PORT": "8080", "POSTGRES_DB": "ctf", "POSTGRES_USER": "ctf",
        "POSTGRES_PASSWORD": password,
        "DATABASE_URL": f"postgresql+psycopg://ctf:{password}@db:5432/ctf",
        "SECRET_KEY": secrets.token_hex(48), "COOKIE_SECURE": "true" if production else "false",
        "CORS_ORIGINS": origin, "SESSION_TTL_HOURS": "24", "REGISTRATION_ENABLED": "true",
        "REDIS_PASSWORD": secrets.token_hex(32), "RATE_LIMIT_BACKEND": "redis",
        "QUEUE_ENABLED": "true", "QUEUE_EAGER": "false", "QUEUE_NAME": "ctf-studio",
        "MAX_UPLOAD_BYTES": "20971520", "MAX_DOCUMENT_BYTES": "2097152",
        "MAX_EXPORT_BYTES": "67108864", "ALLOW_ARCHIVES": "false", "UPLOAD_DIR": "/data/uploads",
        "STORAGE_BACKEND": "s3", "S3_ENDPOINT_URL": "http://minio:9000",
        "S3_BUCKET": "ctf-evidences", "S3_REGION": "us-east-1",
        "MINIO_ROOT_USER": "studio-root-" + secrets.token_hex(8),
        "MINIO_ROOT_PASSWORD": secrets.token_hex(32),
        "S3_ACCESS_KEY": "studio-app-" + secrets.token_hex(8), "S3_SECRET_KEY": secrets.token_hex(32),
        "S3_SIGNED_URL_SECONDS": "60", "AI_ENABLED": "false", "AI_EXTERNAL_ENABLED": "false",
        "OLLAMA_URL": "http://ollama:11434", "OLLAMA_MODEL": "llama3.2:3b",
        "KALI_ENABLED": "false", "KALI_MCP_URL": "http://kali-mcp:8080/mcp",
        "KALI_MCP_TOKEN": secrets.token_hex(32), "KALI_TIMEOUT_SECONDS": "30",
        "KALI_ALLOWED_TOOLS": "system_info,artifact_hash,artifact_file,artifact_strings,artifact_json_summary",
        "METRICS_ENABLED": "true", "METRICS_TOKEN": secrets.token_hex(32), "LOG_LEVEL": "INFO",
        "GRAFANA_ADMIN_USER": "admin", "GRAFANA_ADMIN_PASSWORD": secrets.token_hex(32),
        "GRAFANA_PORT": "3001", "BACKUP_UID": str(os.getuid()), "BACKUP_GID": str(os.getgid()),
        "BACKUP_RETENTION_DAYS": "30", "RPO_TARGET_HOURS": "24", "RTO_TARGET_HOURS": "4",
    }
    values["REDIS_URL"] = f"redis://:{values['REDIS_PASSWORD']}@redis:6379/0"
    return values


def write_private(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as destination:
        destination.write(content)


def test_certificate(origin: str, cert_dir: Path) -> None:
    if urlsplit(origin).hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("Certificado autoassinado de teste só é permitido para loopback")
    cert_dir.mkdir(parents=True, exist_ok=True)
    certificate, key = cert_dir / "fullchain.pem", cert_dir / "privkey.pem"
    if certificate.exists() or key.exists():
        raise ValueError("Certificados existentes são preservados; não serão sobrescritos")
    subprocess.run([
        "openssl", "req", "-x509", "-newkey", "rsa:3072", "-nodes", "-days", "7",
        "-keyout", str(key), "-out", str(certificate), "-subj", "/CN=localhost",
        "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1,IP:::1",
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    key.chmod(0o600)
    certificate.chmod(0o644)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Preparação privada do CTF Writeup Studio")
    parser.add_argument("--production", action="store_true")
    parser.add_argument("--origin", help="Origem pública; produção requer HTTPS")
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--validate", action="store_true", help="Validar configuração existente sem modificá-la")
    parser.add_argument("--self-signed-test", action="store_true", help="TLS loopback para ensaio, sem confiança pública")
    parser.add_argument("--cert-dir", type=Path, default=ROOT / "infra/nginx/certs")
    args = parser.parse_args(argv)
    destination = args.env_file or ROOT / (".env.production" if args.production else ".env")
    try:
        if args.validate or destination.exists():
            values = read_env(destination)
            validate(values, args.production)
            if destination.stat().st_mode & 0o077:
                raise ValueError("Permissões de configuração devem ser 0600 (chmod 600)")
            print("Configuração existente validada e preservada; nenhum segredo foi exibido.")
            return 0
        if args.production and not args.origin:
            raise ValueError("Use --origin https://seu-dominio ao preparar produção")
        origin = (args.origin or "http://localhost:8080").rstrip("/")
        values = generate(args.production, origin)
        validate(values, args.production)
        if args.self_signed_test:
            if not args.production:
                raise ValueError("--self-signed-test exige --production --origin https://localhost")
            test_certificate(origin, args.cert_dir)
        write_private(destination, "# Gerado localmente; não versionar nem compartilhar.\n" +
                      "\n".join(f"{key}={value}" for key, value in values.items()) + "\n")
        (ROOT / "backups").mkdir(mode=0o700, exist_ok=True)
        print("Configuração gerada com permissões 0600 e segredos aleatórios; nenhum segredo foi exibido.")
        if args.production:
            print("TLS: forneça fullchain.pem e privkey.pem válidos em infra/nginx/certs antes de iniciar.")
            if args.self_signed_test:
                print("Certificado loopback de 7 dias criado exclusivamente para teste; não é confiável em produção.")
        return 0
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"Preparação não concluída: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
