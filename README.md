# CTF Writeup Studio

Plataforma open source para organizar CTFs, preservar evidências e produzir writeups técnicos auditáveis. Código próprio sob licença MIT.

## Stack

Next.js/TypeScript, FastAPI/Python, PostgreSQL, Redis/RQ, MinIO/S3, Nginx e Docker Compose. IA Ollama e Kali MCP são opcionais.

## Início rápido

    python scripts/setup.py
    docker compose up -d --build

Acesse http://localhost:8080. API em /api/v1 e OpenAPI em /docs no desenvolvimento.

## Recursos

- Competições, desafios, equipes, papéis e RBAC no backend.
- Writeups com Markdown/rich text, autosave, versões, diff e restauração.
- Evidências com MIME real, SHA-256, versões, anotações e timeline.
- Exportação Markdown, HTML, PDF e JSON.
- Revisão independente, publicação por snapshot e proteção de conteúdo privado.
- IA opcional com proveniência e revisão humana.
- Kali MCP autenticado para coleta tipada de artefatos.
- Observabilidade, backup, restore e CI com PostgreSQL/Redis.

## Verificação

    cd apps/api && pip install -e '.[dev]' && pytest --cov=app --cov-fail-under=80
    cd apps/web && npm ci && npm run typecheck && npm run lint && npm test -- --run && npm run build

Consulte docs/INDEX.md, docs/VALIDATION.md e docs/AUDIT-DEEP-2026-10-29.md.

## Produção

Siga docs/INSTALLATION.md, use docker-compose.prod.yml, TLS válido, serviços privados e secret manager. O pipeline oficial exige API, Web e Backup verdes.

## Licença

MIT. Conteúdo e evidências enviados pertencem aos autores.
