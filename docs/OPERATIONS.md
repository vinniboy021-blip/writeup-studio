# Operação

## Saúde

/api/v1/health confirma processo. /api/v1/ready valida banco, Redis e storage. /api/v1/metrics é somente interno e autenticado; produção bloqueia docs, métricas e readiness no Nginx público.

## Backup e restore

    python scripts/backup.py backup --output backups
    python scripts/backup.py verify --input backups/backup-...
    python scripts/backup.py restore --input backups/backup-... --database-url ... --confirm-replace NOME

Backups incluem dump PostgreSQL, objetos e manifesto SHA-256. Restaure em banco descartável, verifique hashes e registre duração. RPO/RTO são metas, não garantias sem medição.

## Produção

Use TLS válido, PostgreSQL/Redis/MinIO privados, secrets fora do Git, rotação após exposição e retenção documentada. Não exponha serviços internos diretamente. Preserve request ID e hash de evidências em incidentes; não altere originais.
