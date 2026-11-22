# Roadmap

## Status atual (2026-11-22)

Todos os critérios técnicos de release estão atendidos:

- [x] CI verde — API, Web, Backup, E2E (Playwright)
- [x] Zero erros Pyright em toda a `app/`
- [x] Cobertura backend ≥ 80%
- [x] `pip-audit` + `npm audit` sem CVEs high/critical
- [x] Restore de backup comprovado em CI
- [x] OpenAPI versionado e validado em CI
- [x] Dois CVEs corrigidos no lockfile

Itens de governança pendentes (bloqueiam release formal):

- [ ] **A2** — Proteção de branch `main` (requer GitHub Pro para repositório privado)
- [ ] **A3** — Commits assinados por GPG/SSH (requer configuração no ambiente do desenvolvedor)

## Próximas extensões técnicas

| Extensão | Prioridade | Notas |
|---|---|---|
| Workers RQ dedicados (Celery/ARQ) | Média | Atualmente `queue_eager=true` em dev; RQ em prod |
| Editor TipTap com collaborative editing | Média | Substituir textarea Markdown por WYSIWYG com OT |
| Anotação canvas (fabric.js ou Konva) | Média | Substituir o overlay SVG atual |
| Busca full-text com `tsvector` PostgreSQL | Média | ILIKE atual funciona, tsvector melhora performance |
| Trivy / Grype para imagens Docker no CI | Alta | SBOM e scan de vulnerabilidades em imagens |
| SCIM / SSO (SAML 2.0 / OIDC) | Baixa | Para organizações com IdP corporativo |
| Rate limiting distribuído por usuário no Nginx | Média | Hoje por IP; adicionar `$http_x_user_id` |
| Notificações em tempo real (SSE) | Baixa | Hoje polling; SSE via Redis Pub/Sub |

## Critérios para v1.0 (release formal)

1. A2 e A3 fechados (branch protegida + commits assinados)
2. Trivy no CI sem HIGH/CRITICAL em imagens de produção
3. Teste de carga: ≥ 50 usuários concorrentes sem degradação
4. Runbook de incidente documentado e testado
