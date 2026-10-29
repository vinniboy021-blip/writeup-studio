# Testes e validação

Backend:

    cd apps/api
    python -m compileall app
    ruff check app tests
    pytest --cov=app --cov-report=term-missing --cov-fail-under=80

O CI usa PostgreSQL 16 e Redis 7 reais, aplica Alembic e executa a suíte completa. Pyright está disponível para auditoria local; o débito de tipagem deve ser reduzido até voltar ao gate obrigatório.

Frontend:

    cd apps/web
    npm ci
    npm run typecheck
    npm run lint
    npm test -- --run
    npm run build
    npm run test:e2e

O lockfile deve estar sincronizado: npm ci é o comando oficial. Antes de release, execute Docker Compose, backup, restore em banco descartável e verificação de hashes.

Critérios de release: API, Web e Backup verdes; migrations aplicadas; cobertura crítica acima de 80%; dependências e imagens escaneadas; documentação e changelog atualizados.
