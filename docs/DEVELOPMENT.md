# Desenvolvimento

## Estrutura do repositório

```
apps/api/          # FastAPI + Python
  app/
    modules/       # identity, workspace, studio, evidence, integrations
    security.py    # autorização, CSRF, sessões
    config.py      # Settings validado (Pydantic)
    main.py        # composição de rotas e middleware
  alembic/         # migrations
  tests/

apps/web/          # Next.js + TypeScript
  app/             # rotas e páginas (App Router)
  components/
  e2e/             # testes Playwright

scripts/           # setup.py, export_openapi.py, backup.py
infra/nginx/       # nginx.conf, nginx.prod.conf
workers/           # processos RQ separados
docs/              # esta documentação
```

## Configurar ambiente local

```bash
# Sobe serviços de suporte
python scripts/setup.py
docker compose up -d --build

# Backend (desenvolvimento)
cd apps/api
pip install -e '.[dev]'
cp .env.example .env     # ajuste conforme necessário

# Frontend (desenvolvimento)
cd apps/web
npm ci
```

Acesse `http://localhost:8080` (via Nginx) ou diretamente:
- API: `http://localhost:8000/api/v1`
- OpenAPI: `http://localhost:8000/docs`
- Frontend dev: `http://localhost:3000`

## Fluxo de contribuição

1. Crie um branch (`feat/nome`, `fix/nome`, `docs/nome`)
2. Implemente alteração + testes
3. Se a API mudou: `python scripts/export_openapi.py` e commit do `docs/api/openapi.json`
4. Se o modelo mudou: `alembic revision --autogenerate -m "descrição"` e revise o arquivo gerado
5. Execute a suíte completa (veja [TESTING.md](TESTING.md))
6. Abra PR — o CI valida tudo automaticamente

## Regras de arquitetura

- **Rotas** delegam para **services**; services concentram regras de negócio e autorização
- Autorização por recurso fica em `security.py` ou no service do módulo, nunca só na rota
- Modelos SQLAlchemy são compartilhados entre módulos; transações cruzam módulos pelo mesmo `Session`
- Schemas Pydantic definem entrada/saída — nunca exponha modelos ORM diretamente
- Erros preservam `error.code` e `request_id` para rastreabilidade
- Mudanças incompatíveis de API exigem versionamento ou migration documentada

## Variáveis de ambiente para desenvolvimento

```env
ENVIRONMENT=development
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/ctf_dev
SECRET_KEY=development-only-change-this-secret-key
REDIS_URL=redis://localhost:6379/0
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
REGISTRATION_ENABLED=true
```

Consulte [CONFIGURATION.md](CONFIGURATION.md) para todas as variáveis.
