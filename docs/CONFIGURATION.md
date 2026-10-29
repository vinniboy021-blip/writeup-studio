# Configuração

A aplicação lê variáveis do ambiente ou .env. Em produção use secret manager ou .env.production com permissão 0600. Nunca versione tokens, senhas, certificados ou evidências.

## Variáveis essenciais

ENVIRONMENT=production exige PostgreSQL, SECRET_KEY com pelo menos 32 caracteres, CORS_ORIGINS somente HTTPS, COOKIE_SECURE=true, RATE_LIMIT_BACKEND=redis e QUEUE_ENABLED=true. SQLite, CORS wildcard, HTTP e rate limit em memória são rejeitados.

Para MinIO/S3 configure S3_ENDPOINT_URL, S3_BUCKET, S3_ACCESS_KEY, S3_SECRET_KEY, S3_REGION e S3_SIGNED_URL_SECONDS. O bucket deve ser privado.

IA fica desligada por padrão. Ollama usa OLLAMA_URL, OLLAMA_MODEL e AI_TIMEOUT_SECONDS. Provedores externos exigem consentimento explícito.

Kali MCP usa KALI_ENABLED, KALI_MCP_URL, KALI_MCP_TOKEN, KALI_TIMEOUT_SECONDS e KALI_ALLOWED_TOOLS. O bridge aceita somente ferramentas tipadas e artefatos autorizados.

METRICS_ENABLED habilita Prometheus; METRICS_TOKEN deve ser forte quando usado. Em produção Nginx bloqueia métricas, documentação e readiness públicos.

Valide a configuração com:

    python scripts/setup.py --production --origin https://studio.exemplo
    python scripts/setup.py --production --env-file .env.production --validate
    docker compose --env-file .env.production -f docker-compose.yml -f docker-compose.prod.yml config --quiet
