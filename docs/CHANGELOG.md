# Changelog

## Não lançado — 2026-11-22

### Qualidade de código
- `ci.yml`: gate Pyright expandido de 4 módulos críticos para **toda a `app/`** — zero erros obrigatório em CI
- `modules/studio/jobs.py`: guards `is None` após `db.get()` em `execute_export` e `execute_ai`; blocos `except` com variável renomeada para evitar shadowing do `row` original
- `modules/studio/routes.py`: checks explícitos de `None` para `Challenge`, `WriteupTemplate` e `Evidence` após `db.get()`; tipo `actor: User | None` em `get_publication` com guard antes de `authorize()`; `type: ignore[union-attr]` nos `rowcount` SQLAlchemy
- `modules/integrations/kali_bridge.py`: `summary` tipado como `dict[str, object]`; `params.get("name", "")` com default; `type: ignore[attr-defined]` para `anyio.to_thread`
- `modules/evidence/service.py`: `type: ignore[arg-type]` em `SpooledTemporaryFile` passado para `validate_file` e `put_object`; `type: ignore[union-attr]` nos `rowcount` × 2
- `modules/evidence/routes.py`: `type: ignore[union-attr]` no `rowcount`
- `modules/evidence/rendering.py`: `shape.x2 or 0.0` e `shape.y2 or 0.0` para coordenadas de seta; `shape.text or ""` para texto
- `modules/workspace/services.py`: `getattr()` em vez de acesso direto a `model.description` e `model.notes` dentro de `hasattr()`
- `cli.py`: variável `active_user: User` com `assert user is not None` explícitos; elimina ambiguidade de `user: User | None`
- `config.py`: anotação `-> Self` no `model_validator`; `type: ignore[call-arg]` no singleton `Settings()`

### Segurança
- `config.py`: `METRICS_TOKEN` obrigatório (≥ 16 chars) em produção quando `METRICS_ENABLED=true`
- `ci.yml`: `pip-audit` contra `requirements.lock` e `npm audit --audit-level=high` como steps bloqueantes
- `ci.yml`: job E2E com Playwright Chromium + stack completo (PostgreSQL + Redis + API + Next.js)
- `ci.yml`: verificação de divergência do `docs/api/openapi.json` em cada build de API
- `ci.yml`: restore completo de backup habilitado em CI via `TEST_BACKUP_PG_ADMIN_URL`
- `requirements.lock`: `dnspython 2.9.0 → 2.9.2` (CVE-2026-128089); `opentelemetry-api 1.45.1 → 1.45.2` (CVE-2026-126360)

### Testes
- `apps/web/e2e/auth.spec.ts`: smoke tests E2E de registro, login, logout e senha incorreta

### Documentação
- `OPERATIONS.md`: procedimento de rotação de credenciais e comportamento do cache S3; rate limit por IP atrás de Nginx
- `README.md`, `CONTRIBUTING.md`, `SECURITY.md`: revisão e expansão
- `docs/DEVELOPMENT.md`, `docs/TESTING.md`, `docs/CONFIGURATION.md`: revisão e expansão

## 0.1.0

Fundação FastAPI/Next.js, autenticação Argon2id, workspace com equipes e RBAC, writeups versionados com diff/restore, evidências com hash SHA-256 e MIME real, anotações e timeline, comentários e revisões independentes, exportações (Markdown, HTML, PDF, JSON), Kali MCP configurável, Docker Compose com Nginx, CI com PostgreSQL/Redis reais, backup com manifesto de integridade e documentação completa.
