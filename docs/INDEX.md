# Documentação do CTF Writeup Studio

O código e os guias descrevem um monólito modular com API FastAPI, frontend Next.js, PostgreSQL, armazenamento privado de evidências e jobs RQ. A licença do código próprio é MIT; serviços e dependências mantêm suas licenças originais.

| Documento | Finalidade |
|---|---|
| [Instalação](INSTALLATION.md) | Ambiente local, Docker e configuração de produção |
| [Configuração](CONFIGURATION.md) | Variáveis, limites, credenciais e integrações opt-in |
| [Guia do usuário](USER-GUIDE.md) | Competições, editor, evidências e revisão |
| [API](API.md) | Sessões, CSRF, paginação, concorrência e exemplos |
| [Arquitetura](ARCHITECTURE.md) | Componentes, responsabilidades e decisões técnicas |
| [Modelo de dados](DATABASE.md) | Relações, migrations e isolamento |
| [Desenvolvimento](DEVELOPMENT.md) | Ambiente, módulos, testes e contribuições |
| [Segurança](SECURITY.md) | Permissões, uploads, publicação e fronteiras de confiança |
| [Operação](OPERATIONS.md) | Jobs, monitoramento, manutenção e recuperação |
| [Backup e restore](BACKUP-RESTORE.md) | Banco/objetos, integridade e ensaio isolado |
| [Kali MCP](KALI-MCP.md) | Bridge autenticado, protocolo e proveniência |
| [IA](AI.md) | Ollama, consentimento externo, fontes e revisão humana |
| [Testes](TESTING.md) | Estratégia e comandos reproduzíveis |
| [Validação](VALIDATION.md) | Evidências dos testes realmente executados |
| [Troubleshooting](TROUBLESHOOTING.md) | Diagnóstico de configuração e operação |
| [Roadmap](ROADMAP.md) | Extensões opcionais e critérios para releases |
| [Histórico](CHANGELOG.md) | Alterações desta implementação |

OpenAPI de desenvolvimento: `/docs`, `/redoc` e `/openapi.json`. Os contratos usados pelo frontend estão em [contracts.md](contracts.md); a especificação gerada em `docs/api/openapi.json` é produzida pelo script de exportação após a composição da API.
