"""Validated runtime settings. No infrastructure is created on import."""

from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    environment: Literal["development", "test", "production"] = "development"
    database_url: str = "sqlite:///./data/ctf.db"
    secret_key: str = "development-only-change-this-secret-key"
    redis_url: str = "redis://redis:6379/0"
    session_ttl_hours: int = Field(24, ge=1, le=720)
    cookie_secure: bool = False
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    login_rate_limit: int = Field(8, ge=1, le=100)
    login_rate_window_seconds: int = Field(60, ge=10, le=3600)
    rate_limit_backend: Literal["memory", "redis"] = "memory"
    registration_enabled: bool = True
    allow_archives: bool = False
    max_upload_bytes: int = Field(20 * 1024 * 1024, ge=1024, le=1024 * 1024 * 1024)
    max_document_bytes: int = Field(2 * 1024 * 1024, ge=1024, le=10 * 1024 * 1024)
    max_export_bytes: int = Field(64 * 1024 * 1024, ge=1024)
    upload_dir: str = "./data/uploads"
    storage_backend: Literal["local", "s3"] = "local"
    s3_endpoint_url: str = ""
    s3_bucket: str = "ctf-evidences"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_region: str = "us-east-1"
    s3_signed_url_seconds: int = Field(60, ge=10, le=300)
    queue_enabled: bool = False
    queue_eager: bool = False
    queue_name: str = "ctf-studio"
    export_job_timeout: int = Field(180, ge=10, le=1800)
    ai_enabled: bool = False
    ollama_url: str = "http://ollama:11434"
    ollama_model: str = "llama3.2:3b"
    ai_timeout_seconds: int = Field(120, ge=5, le=1800)
    ai_external_enabled: bool = False
    ai_external_url: str = ""
    ai_external_token: str = ""
    ai_external_model: str = ""
    ai_max_input_chars: int = Field(100000, ge=1000, le=1000000)
    ai_max_jobs_per_hour: int = Field(10, ge=1, le=1000)
    kali_enabled: bool = False
    kali_mcp_url: str = ""
    kali_mcp_token: str = ""
    kali_timeout_seconds: int = Field(30, ge=1, le=300)
    kali_max_output_bytes: int = Field(1024 * 1024, ge=1024, le=20 * 1024 * 1024)
    kali_allowed_tools: str = "system_info,artifact_hash,artifact_file,artifact_strings,artifact_json_summary"
    kali_max_artifact_bytes: int = Field(20 * 1024 * 1024, ge=1024, le=100 * 1024 * 1024)
    kali_max_jobs_per_minute: int = Field(5, ge=1, le=100)
    kali_bridge_token: str = ""
    kali_shared_root: str = "/evidences"
    metrics_enabled: bool = True
    metrics_token: str = ""
    log_level: str = "INFO"
    retention_days: int = Field(90, ge=1, le=36500)

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip().rstrip("/") for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def max_upload_mb(self) -> int:
        return self.max_upload_bytes // (1024 * 1024)

    @property
    def storage_path(self) -> str:
        return self.upload_dir

    @model_validator(mode="after")
    def validate_runtime(self):
        for origin in self.allowed_origins:
            parsed = urlsplit(origin)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.path or parsed.query:
                raise ValueError("CORS_ORIGINS deve conter origens HTTP(S) explícitas")
        if not self.allowed_origins or "*" in self.allowed_origins:
            raise ValueError("CORS_ORIGINS não pode ser vazio ou wildcard")
        if self.environment == "production":
            if not self.cookie_secure:
                raise ValueError("COOKIE_SECURE=true é obrigatório em produção")
            if not self.database_url.startswith(("postgresql://", "postgresql+psycopg://")):
                raise ValueError("PostgreSQL é obrigatório em produção")
            if len(self.secret_key) < 32 or self.secret_key.startswith(("development", "change-me")):
                raise ValueError("SECRET_KEY forte com pelo menos 32 caracteres é obrigatório")
            if self.rate_limit_backend != "redis":
                raise ValueError("RATE_LIMIT_BACKEND=redis é obrigatório em produção")
            if any(not origin.startswith("https://") for origin in self.allowed_origins):
                raise ValueError("CORS_ORIGINS deve usar HTTPS em produção")
            if self.queue_eager:
                raise ValueError("QUEUE_EAGER não pode ser habilitado em produção")
            if not self.queue_enabled:
                raise ValueError("QUEUE_ENABLED=true é obrigatório em produção")
            if self.metrics_enabled and len(self.metrics_token) < 16:
                raise ValueError("METRICS_TOKEN com pelo menos 16 caracteres é obrigatório em produção quando métricas estão habilitadas")
        if self.queue_enabled or self.rate_limit_backend == "redis":
            if not self.redis_url.startswith(("redis://", "rediss://")):
                raise ValueError("REDIS_URL inválida")
        if self.kali_enabled and not self.kali_mcp_url:
            raise ValueError("KALI_MCP_URL obrigatório quando Kali está habilitado")
        if self.storage_backend == "s3" and not self.s3_bucket:
            raise ValueError("S3_BUCKET obrigatório")
        for value in (self.ollama_url, self.kali_mcp_url, self.s3_endpoint_url, self.ai_external_url):
            if value:
                parsed = urlsplit(value)
                if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
                    raise ValueError("URLs de serviços devem ser HTTP(S), sem credenciais embutidas")
        if not Path(self.upload_dir).as_posix():
            raise ValueError("UPLOAD_DIR inválido")
        return self


settings = Settings()
