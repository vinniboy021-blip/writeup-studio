# Desenvolvimento

Backend: apps/api/app. Frontend: apps/web. Migrations: apps/api/alembic. Workers: workers. Scripts operacionais: scripts. Infraestrutura: infra.

Toda alteração de modelo exige migration, autorização, teste e documentação. Controllers devem delegar regras aos serviços e políticas.

Ambiente:

    python scripts/setup.py
    docker compose up -d --build
    cd apps/api && pip install -e '.[dev]'
    cd ../web && npm ci

Fluxo: crie branch, altere código e documentação, execute testes, atualize OpenAPI com scripts/export_openapi.py, revise migrations e abra pull request. Não faça push direto em main quando a proteção estiver habilitada.

A API usa /api/v1. Erros devem preservar error.code e request_id. Mudanças incompatíveis exigem nova versão ou migração documentada.
