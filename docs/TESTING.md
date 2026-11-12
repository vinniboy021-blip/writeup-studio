# Testes

## Backend

```bash
cd apps/api

# Compilação e linting
python -m compileall app
ruff check app tests --ignore E702,F401

# Typecheck nos módulos críticos de segurança
pyright app/security.py app/modules/identity/services.py \
         app/modules/identity/routes.py app/modules/evidence/validation.py

# Auditoria de dependências
pip-audit -r requirements.lock --progress-spinner off

# Suíte de testes (requer PostgreSQL e Redis ativos)
pytest --cov=app --cov-report=term-missing --cov-fail-under=80
```

Variáveis necessárias para os testes:

```env
ENVIRONMENT=test
DATABASE_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:5432/ctf_test
TEST_REDIS_URL=redis://127.0.0.1:6379/0
```

## Frontend

```bash
cd apps/web

npm run typecheck   # tsc --noEmit
npm run lint        # ESLint
npm test -- --run   # Vitest (unitários)
npm run build       # build de produção

# Auditoria de dependências
npm audit --audit-level=high
```

## E2E (Playwright)

Requer API e frontend rodando:

```bash
# Terminal 1 — API
cd apps/api
ENVIRONMENT=development \
DATABASE_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:5432/ctf_e2e \
SECRET_KEY=e2e-test-secret-key-for-ci-use-only-32ch \
CORS_ORIGINS=http://127.0.0.1:3000 \
REDIS_URL=redis://127.0.0.1:6379/0 \
RATE_LIMIT_BACKEND=memory \
COOKIE_SECURE=false \
REGISTRATION_ENABLED=true \
METRICS_TOKEN=e2e-ci-metrics-placeholder \
uvicorn app.main:app --host 127.0.0.1 --port 8000

# Terminal 2 — Frontend
cd apps/web
API_INTERNAL_URL=http://127.0.0.1:8000 npm run dev -- --port 3000

# Terminal 3 — Testes
cd apps/web
npx playwright install chromium --with-deps
PLAYWRIGHT_BASE_URL=http://127.0.0.1:3000 npm run test:e2e
```

O relatório Playwright fica em `apps/web/playwright-report/`. No CI é salvo como artefato em caso de falha.

## CI

O pipeline `.github/workflows/ci.yml` executa quatro jobs independentes:

| Job | O que valida |
|---|---|
| `api` | Linting, Pyright, pip-audit, pytest, OpenAPI diff |
| `web` | typecheck, lint, Vitest, npm audit, build |
| `backup` | Integridade do backup/restore |
| `e2e` | Fluxo completo register → login → logout via Playwright |

Todos os jobs usam serviços reais (PostgreSQL 16 + Redis 7). Nenhum mock de banco de dados.

## Critérios de release

- Jobs api, web, backup e e2e verdes
- Cobertura de backend ≥ 80%
- Migrations aplicadas sem erro
- `pip-audit` e `npm audit` sem vulnerabilidades high/critical
- `docs/api/openapi.json` sincronizado com a API real
- Changelog atualizado
