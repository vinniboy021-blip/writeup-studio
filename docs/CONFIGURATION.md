# Configuração

A aplicação lê variáveis do ambiente ou de um arquivo `.env`. Em produção use um secret manager ou `.env.production` com permissão `0600`. Nunca versione tokens, senhas, certificados ou evidências.

## Variáveis essenciais

| Variável | Padrão | Descrição |
|---|---|---|
| `ENVIRONMENT` | `development` | `development`, `test` ou `production` |
| `DATABASE_URL` | SQLite local | URL PostgreSQL obrigatória em produção |
| `SECRET_KEY` | valor fraco | Mínimo 32 chars; rejeitado se começar com `development` |
| `CORS_ORIGINS` | localhost:3000 | Origens HTTP(S) explícitas, separadas por vírgula |
| `COOKIE_SECURE` | `false` | `true` obrigatório em produção |
| `RATE_LIMIT_BACKEND` | `memory` | `redis` obrigatório em produção |
| `REDIS_URL` | redis://redis:6379/0 | Obrigatório quando Redis for backend |
| `REGISTRATION_ENABLED` | `true` | Desabilite após criar contas iniciais |
| `SESSION_TTL_HOURS` | `24` | 1–720 horas |

## Storage S3 / MinIO

| Variável | Descrição |
|---|---|
| `STORAGE_BACKEND` | `local` (dev) ou `s3` (produção) |
| `S3_ENDPOINT_URL` | URL do MinIO ou AWS S3 |
| `S3_BUCKET` | Nome do bucket (deve ser privado) |
| `S3_ACCESS_KEY` | Credencial de acesso |
| `S3_SECRET_KEY` | Chave secreta |
| `S3_REGION` | Região (padrão `us-east-1`) |
| `S3_SIGNED_URL_SECONDS` | Validade de URLs assinadas: 10–300 s |

## Métricas (Prometheus)

| Variável | Padrão | Descrição |
|---|---|---|
| `METRICS_ENABLED` | `true` | Habilita endpoint `/api/v1/metrics` |
| `METRICS_TOKEN` | vazio | Obrigatório em produção: mínimo 16 chars |

Em produção o Nginx bloqueia `/api/v1/metrics` publicamente. A validação no `config.py` garante um token forte mesmo que o Nginx seja reconfigurado.

## IA (opcional)

| Variável | Descrição |
|---|---|
| `AI_ENABLED` | Habilita Ollama local |
| `OLLAMA_URL` | URL do serviço Ollama |
| `OLLAMA_MODEL` | Modelo (padrão `llama3.2:3b`) |
| `AI_EXTERNAL_ENABLED` | Requer consentimento explícito por job |
| `AI_EXTERNAL_URL` | URL do provedor externo |
| `AI_EXTERNAL_TOKEN` | Token do provedor |
| `AI_MAX_INPUT_CHARS` | Limite de entrada: 1 000–1 000 000 chars |

## Kali MCP (opcional)

| Variável | Descrição |
|---|---|
| `KALI_ENABLED` | Habilita o bridge |
| `KALI_MCP_URL` | URL do servidor MCP |
| `KALI_MCP_TOKEN` | Token de autenticação do MCP |
| `KALI_BRIDGE_TOKEN` | Token do bridge local |
| `KALI_ALLOWED_TOOLS` | Lista separada por vírgula das ferramentas permitidas |
| `KALI_MAX_ARTIFACT_BYTES` | Limite de bytes por artefato (padrão 20 MB) |
| `KALI_TIMEOUT_SECONDS` | Timeout por operação: 1–300 s |

## Uploads

| Variável | Padrão | Descrição |
|---|---|---|
| `MAX_UPLOAD_BYTES` | 20 MB | Limite por evidência (máx 1 GB) |
| `MAX_DOCUMENT_BYTES` | 2 MB | Limite por documento (máx 10 MB) |
| `ALLOW_ARCHIVES` | `false` | Habilita ZIP/tar (nunca extrai automaticamente) |
| `UPLOAD_DIR` | `./data/uploads` | Diretório local quando `STORAGE_BACKEND=local` |

## Validação

```bash
# Validar configuração de produção
python scripts/setup.py --production --origin https://studio.exemplo

# Validar arquivo .env existente
python scripts/setup.py --production --env-file .env.production --validate

# Validar docker-compose.prod.yml
docker compose --env-file .env.production \
  -f docker-compose.yml -f docker-compose.prod.yml config --quiet
```

## Rotação de credenciais

Consulte [OPERATIONS.md](OPERATIONS.md) para o procedimento de rotação e o comportamento do cache S3 durante restarts.
