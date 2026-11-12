# Documentação do CTF Writeup Studio

Monólito modular com API FastAPI, frontend Next.js, PostgreSQL, armazenamento privado de evidências e jobs RQ. Código próprio sob licença MIT; dependências e serviços mantêm suas licenças originais.

## Guias principais

| Documento | Finalidade |
|---|---|
| [Instalação](INSTALLATION.md) | Ambiente local, Docker e configuração de produção |
| [Configuração](CONFIGURATION.md) | Todas as variáveis de ambiente, limites e integrações |
| [Desenvolvimento](DEVELOPMENT.md) | Estrutura, ambiente, fluxo de contribuição e regras de arquitetura |
| [Testes](TESTING.md) | Suíte backend, frontend, E2E Playwright e critérios de release |
| [Operação](OPERATIONS.md) | Saúde, backup, rotação de credenciais e rate limiting |
| [Troubleshooting](TROUBLESHOOTING.md) | Diagnóstico de configuração e operação |

## Referência técnica

| Documento | Finalidade |
|---|---|
| [Arquitetura](ARCHITECTURE.md) | Componentes, fluxos e decisões técnicas |
| [Segurança](SECURITY.md) | Autenticação, RBAC, evidências e publicação |
| [API](API.md) | Sessões, CSRF, paginação, concorrência e exemplos |
| [Modelo de dados](DATABASE.md) | Relações, migrations e isolamento |
| [Contratos](contracts.md) | Schemas usados pelo frontend |
| [Kali MCP](KALI-MCP.md) | Bridge autenticado, protocolo e proveniência |
| [IA](AI.md) | Ollama, consentimento externo, fontes e revisão humana |

## Guia do usuário

| Documento | Finalidade |
|---|---|
| [Guia do usuário](USER-GUIDE.md) | Competições, editor, evidências e revisão |

## Histórico e planejamento

| Documento | Finalidade |
|---|---|
| [Changelog](CHANGELOG.md) | Alterações desta implementação |
| [Roadmap](ROADMAP.md) | Extensões opcionais e critérios para releases |
| [Auditoria de segurança](AUDIT-DEEP-2026-10-29.md) | Findings e status de remediação |

## OpenAPI

- Desenvolvimento: `/docs`, `/redoc` e `/openapi.json` (servidor local)
- Gerada: `docs/api/openapi.json` — mantida sincronizada pelo CI via `scripts/export_openapi.py`
