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

## Rotação de credenciais

As configurações (`SECRET_KEY`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `KALI_MCP_TOKEN`) são lidas do ambiente na inicialização e mantidas em memória durante o ciclo de vida do processo. O cliente S3 é instanciado por conjunto de credenciais via cache interno.

**Após rotacionar qualquer credencial, reinicie todos os contêineres API** para que os novos valores sejam carregados. Um rolling restart é suficiente; o Redis preserva sessões entre restarts.

Procedimento de rotação de `SECRET_KEY`:
1. Gere novo valor: `python -c "import secrets; print(secrets.token_urlsafe(48))"`
2. Atualize a secret no seu gerenciador de segredos
3. Reinicie os contêineres API (sessões existentes tornam-se inválidas; usuários precisam fazer login novamente)

## Rate limit por IP

O rate limit de autenticação (`login_rate_limit * 10` por janela) usa o IP do peer TCP direto (`request.client.host`). Em topologias com Nginx na mesma rede Docker Compose, todos os clientes compartilham o IP do Nginx como peer — a proteção por IP torna-se global. O rate limit por **conta de e-mail** (`login_rate_limit`) é o controle primário e funciona corretamente em qualquer topologia.

Se proteção por IP real for necessária, configure `trusted_proxy = <IP-do-Nginx>` e implemente leitura controlada do header `X-Real-IP` via `set_real_ip_from` no Nginx.
