# Operação

## Saúde e observabilidade

- `/api/v1/health` confirma que o processo responde.
- `/api/v1/ready` valida banco e armazenamento configurado.
- `/api/v1/metrics` deve ficar em rede interna; em produção o Nginx a bloqueia.
- Logs possuem JSON, request ID e latência, sem conteúdo de evidências.

## Backup e restore

Execute `python scripts/backup.py backup --output backups`, depois `verify` e um restore em banco descartável. Preserve o manifesto SHA-256 e registre a duração. Nunca use `--replace-objects` sem confirmar o bucket/diretório de destino. O restore exige `--confirm-replace` igual ao nome do banco.

RPO/RTO são metas configuráveis, não garantias. Faça um teste de restauração pelo menos mensalmente e antes de uma migração importante.

## Produção

Use somente `.env.production` com permissões 0600, HTTPS válido e PostgreSQL/Redis privados. Não exponha API, banco, Redis, MinIO, Grafana ou MCP diretamente à internet. Rotacione tokens e segredos após qualquer suspeita de exposição.
