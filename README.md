# CTF Writeup Studio

Plataforma para organizar competições CTF, preservar evidências e produzir writeups técnicos auditáveis. Código próprio sob licença MIT.

## Stack

| Camada | Tecnologia |
|---|---|
| Frontend | Next.js 15 + TypeScript |
| Backend | FastAPI + Python 3.12 |
| Banco | PostgreSQL 16 |
| Cache / filas | Redis 7 + RQ |
| Storage | MinIO / S3 compatível |
| Proxy | Nginx |
| Orquestração | Docker Compose |
| IA (opcional) | Ollama local ou provedor externo com consentimento |
| Análise (opcional) | Kali MCP bridge autenticado |

## Início rápido

```bash
python scripts/setup.py
docker compose up -d --build
```

Acesse `http://localhost:8080`. Em desenvolvimento a OpenAPI fica em `/docs` e `/redoc`.

## Funcionalidades

- Competições, desafios, equipes com RBAC (gestor, editor, revisor, visualizador)
- Editor Markdown com autosave, versões imutáveis, diff e restauração
- Evidências com MIME real via `libmagic`, SHA-256, anotações e timeline
- Revisão independente com snapshot por versão aprovada
- Exportação em Markdown, HTML, PDF e JSON
- IA opcional com proveniência e revisão humana obrigatória
- Kali MCP autenticado para coleta tipada de artefatos
- Backup com dump PostgreSQL + objetos + manifesto SHA-256
- CI com PostgreSQL/Redis reais, Pyright, pip-audit, npm audit e E2E Playwright

## Verificação

```bash
# Backend
cd apps/api
pip install -e '.[dev]'
pytest --cov=app --cov-report=term-missing --cov-fail-under=80

# Frontend
cd apps/web
npm ci
npm run typecheck && npm run lint && npm test -- --run && npm run build
```

## Produção

Siga [docs/INSTALLATION.md](docs/INSTALLATION.md), use `docker-compose.prod.yml`, TLS válido, serviços privados e secret manager. O pipeline exige jobs **api**, **web**, **backup** e **e2e** verdes antes de merge.

## Documentação

Consulte [docs/INDEX.md](docs/INDEX.md) para o índice completo.

## Licença

MIT. Conteúdo e evidências enviados pertencem aos seus autores.
