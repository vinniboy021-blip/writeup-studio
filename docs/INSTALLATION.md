# Instalação

## Requisitos

Docker com Compose v2.24.4+ para os arquivos de produção que usam `!override`. Para desenvolvimento sem containers: Python 3.11+, Node.js 22+, libmagic, PostgreSQL/Redis quando habilitados e armazenamento local protegido ou S3. Os volumes guardam os dados; não use `docker compose down -v` para desligamento rotineiro.

## Instalação local com Docker

```sh
python scripts/setup.py
docker compose config --quiet
docker compose up -d --build
docker compose ps
```

O script gera `.env` com segredos aleatórios e permissões 0600. Se o arquivo já existe, ele é validado e preservado. Não use exemplos com senhas conhecidas em produção. A interface abre em **http://localhost:8080**; Nginx serve web e `/api/v1` na mesma origem. Banco, Redis, MinIO e API não têm portas públicas no Compose padrão.

O serviço `minio-init` cria o bucket privado e um usuário de aplicação limitado; `migrate` aplica Alembic antes de API/worker. Se qualquer inicialização falhar, consulte `docker compose logs migrate minio-init api worker`.

OpenAPI está em http://localhost:8080/docs quando o proxy permite a rota de documentação; diretamente na API de desenvolvimento, `/docs`, `/redoc` e `/openapi.json`. O proxy de produção não deve expor a documentação administrativa indiscriminadamente.

## Primeiro administrador

O registro cria usuários comuns. Crie um administrador por console local autenticado:

```sh
docker compose exec api python -m app.cli create-admin --email seu-email@example.org --name Administrador
```

A senha é solicitada sem eco. Para contas legadas ou recuperação administrativa:

```sh
docker compose exec api python -m app.cli reset-password --email seu-email@example.org
```

Não inclua senha em argumento de processo. A CLI admite stdin para automação por secret manager. Administradores existentes podem gerir usuários pela interface/API.

## Produção com HTTPS

```sh
python scripts/setup.py --production --origin https://studio.seu-dominio.example
# Forneça o certificado do seu domínio em infra/nginx/certs/fullchain.pem
# e a chave privada em infra/nginx/certs/privkey.pem.
python scripts/setup.py --production --env-file .env.production --validate
docker compose --env-file .env.production -f docker-compose.yml -f docker-compose.prod.yml config --quiet
docker compose --env-file .env.production -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

O endereço de exemplo deve ser substituído por um domínio controlado pela operação. O overlay força produção, cookies Secure, fila Redis e CORS HTTPS. Nginx redireciona HTTP para HTTPS e utiliza os certificados fornecidos. Gerencie renovação por ACME ou sua infraestrutura; a plataforma não obtém um domínio nem certificado público automaticamente. `--self-signed-test` é exclusivamente um ensaio de loopback, não certificado confiável de produção.

## Sem Docker

```sh
python -m venv .venv
. .venv/bin/activate
pip install -e 'apps/api[dev]'
export DATABASE_URL=sqlite:///./data/local.db
export STORAGE_BACKEND=local
export QUEUE_ENABLED=false
export RATE_LIMIT_BACKEND=memory
cd apps/api
alembic upgrade head
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Em outro terminal:

```sh
cd apps/web
npm ci
API_INTERNAL_URL=http://127.0.0.1:8000 npm run dev
```

Abra http://localhost:3000. Configure `CORS_ORIGINS` para essa origem. Em implantação real use PostgreSQL, Redis e os mesmos limites/políticas de produção. Um `.env` gerado para Compose aponta para hostnames de containers; não reutilize esses endereços como se fossem serviços locais.

## Integrações opcionais

Ative os profiles `kali`, `ai` e `monitoring` somente quando necessários. Os toggles de aplicação também precisam ser configurados; iniciar um container não autoriza automaticamente uma integração. Consulte [Kali MCP](KALI-MCP.md), [IA](AI.md) e [Operação](OPERATIONS.md).
