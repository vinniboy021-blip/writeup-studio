# Remediação da auditoria — 2026-10-26

Ações aplicadas após o relatório `docs/AUDIT-2026-10-26.md`:

- CI agora instala dependências de desenvolvimento, executa migrations, PostgreSQL/Redis reais, Ruff, Pyright, pytest com cobertura mínima de 80%, typecheck/lint/Vitest/build frontend e testes de backup.
- O job de backup recebe `TEST_BACKUP_PG_ADMIN_URL` e exercita bancos descartáveis quando o runner oferece `pg_dump` e `pg_restore`.
- Foi adicionado `apps/api/requirements.lock`, gerado por uv com hashes, e o CI/Dockerfile passaram a instalar com `--require-hashes`.
- O `.gitignore` agora cobre caches em qualquer profundidade; artefatos `.pytest_cache` publicados foram removidos da branch.
- `docs/KALI-MCP.md` foi reescrito conforme as cinco ferramentas tipadas e o protocolo JSON-RPC real; não há mais contrato de execução `exec`.
- `docs/TESTING.md` e `docs/OPERATIONS.md` agora descrevem comandos, serviços necessários e limites de evidência.
- Produção exige `METRICS_TOKEN` forte quando métricas estão habilitadas, e o setup passa a gerar esse token.

Validação remota realizada: os arquivos corrigidos existem na branch `main`; o lockfile possui hashes para as dependências resolvidas. A execução dos jobs GitHub Actions depende do runner do repositório e deve ser confirmada pelo status do workflow após o próximo push.
