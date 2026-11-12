# Changelog

## Não lançado

### Segurança
- `config.py`: `METRICS_TOKEN` obrigatório (≥ 16 chars) em produção quando `METRICS_ENABLED=true` — defesa em profundidade além do bloqueio Nginx
- `ci.yml`: Pyright obrigatório nos módulos críticos de segurança (`security.py`, módulos `identity` e `evidence/validation.py`)
- `ci.yml`: `pip-audit` contra `requirements.lock` e `npm audit --audit-level=high` como steps bloqueantes
- `ci.yml`: job E2E com Playwright Chromium + stack completo (PostgreSQL + Redis + API + Next.js)
- `ci.yml`: verificação de divergência do `docs/api/openapi.json` em cada build de API

### Documentação
- `OPERATIONS.md`: procedimento de rotação de credenciais e comportamento do cache S3; limitação do rate limit por IP atrás de Nginx
- `README.md`, `CONTRIBUTING.md`, `SECURITY.md`: revisão e expansão
- `docs/DEVELOPMENT.md`, `docs/TESTING.md`, `docs/CHANGELOG.md`, `docs/CONFIGURATION.md`: revisão e expansão

### Testes
- `apps/web/e2e/auth.spec.ts`: smoke tests E2E de registro, login, logout e senha incorreta

## 0.1.0

Fundação FastAPI/Next.js, autenticação Argon2id, workspace com equipes e RBAC, writeups versionados com diff/restore, evidências com hash SHA-256 e MIME real, anotações e timeline, comentários e revisões independentes, exportações (Markdown, HTML, PDF, JSON), Kali MCP configurável, Docker Compose com Nginx, CI com PostgreSQL/Redis reais, backup com manifesto de integridade e documentação completa.
