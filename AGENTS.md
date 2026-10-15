# CTF Writeup Studio

- Licença MIT e API `/api/v1`; português na interface e documentação.
- Backend monólito modular FastAPI, SQLAlchemy 2 e Alembic; PostgreSQL em produção.
- Canonical document v1: `{schema_version:1,sections:[{id,title,markdown}]}`. Validar schema, tamanho e IDs únicos.
- IDs UUID string; timestamps UTC; todas relações verificadas no servidor.
- Sessões HttpOnly; CSRF obrigatório em mutações autenticadas. Argon2id obrigatório.
- Recursos privados só owner/admin; recursos team são limitados à equipe e papel. Público usa snapshots autorizados separados.
- Writeups usam atualização condicional atômica `id/version` no banco; cada save cria revisão na mesma transação. HTTP 409 em conflito.
- Evidências originais imutáveis; anotação validada e derivado separado. Download autenticado.
- IA opcional por Ollama; fatos e inferências/proveniência separados, consentimento externo explícito e revisão humana.
- Kali MCP opcional: conexão configurada pela operação, sem endpoints escolhidos por usuários, argv sem shell, escopo de arquivos/evidências, auditoria.
- Nunca declarar testes executados sem saída real; documentação deve descrever comportamento existente.
- Evitar mudanças em arquivos de outro agente; combinar contratos por mensagens.

## Interfaces

`app.config.settings` Pydantic Settings. `app.db.Base`, `engine`, `SessionLocal`, `get_db`.
`app.models` modelos compartilhados; `app.schemas.Document`, `Section`, safe UserOut.
`app.security.get_actor`, `require_csrf`, `authorize(db,actor,resource,action='read')`,
`authorize_team(db,actor,team_id,action='read')`, `visible_query(stmt,Model,actor,db)`, `audit(db,actor,action,entity_type,entity_id,details=None)`.
Cada módulo exporta APIRouter `router` em `app.modules.<module>.routes`.

Contrato frontend/backend: `docs/contracts.md`.
