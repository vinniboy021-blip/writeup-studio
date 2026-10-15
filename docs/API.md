# API REST

Base `/api/v1`. A referência completa de schemas, parâmetros e respostas é [api/openapi.json](api/openapi.json), gerada pela composição real do FastAPI. `/docs` e `/redoc` estão habilitados no desenvolvimento. Execute `python scripts/export_openapi.py` para atualizar a referência após alterar rotas/schemas.

## Sessões

Registro e login retornam `{user,csrf_token}` e definem `ctf_session` HttpOnly. `GET /auth/me` recupera usuário e token CSRF para a sessão atual. O navegador usa `credentials: include`; JavaScript não lê o cookie. Toda mutação autenticada envia `X-CSRF-Token`. Logout/revogação tornam a sessão inválida no banco; alterar senha revoga sessões conforme o fluxo da API.

```http
POST /api/v1/auth/register
Content-Type: application/json

{"name":"Seu nome","email":"voce@example.org","password":"uma-senha-longa-escolhida-por-voce"}
```

Emails/senhas no exemplo são ilustrativos; não são contas pré-instaladas. Registro pode ser desabilitado pela operação. `GET /auth/sessions` e `DELETE /auth/sessions/{id}` permitem revisar/revogar sessões próprias.

## Paginação e erros

Listagens retornam `{items,total,page,page_size}`. Os limites são validados por rota; valores fora dos limites retornam 422. Erros da aplicação incluem `error.code`, `error.message`, detalhes seguros e `request_id`; entradas de validação não refletem senhas ou documentos completos no erro. Use o identificador de requisição para correlação com logs.

| HTTP | Significado |
|---|---|
| 201/202 | Recurso criado / job aceito |
| 401 | Sessão ausente, revogada ou expirada |
| 403/404 | Ação não permitida / recurso não encontrado ou privado |
| 409 | Conflito de versão, integridade ou aprovação obsoleta |
| 413/415 | Limite de tamanho / tipo real não permitido |
| 422 | Entrada/schema/relação inválida |
| 428 | Confirmação de execução ausente |
| 429 | Limite de consumo/tentativas excedido |
| 502/503 | Integração falhou / serviço desabilitado ou dependência indisponível |

## Documento e CAS

```json
{
  "expected_version": 3,
  "title": "Título revisado",
  "document": {
    "schema_version": 1,
    "sections": [{"id": "objective", "title": "Objetivo", "markdown": "Observações fornecidas pelo autor."}]
  }
}
```

Envie esse corpo ao `PATCH /writeups/{id}`. Somente uma requisição com versão 3 pode criar versão 4. Um 409 exige obter a versão atual e revisar/mesclar o rascunho; repetir automaticamente a versão antiga não resolve o conflito. `GET /writeups/{id}/revisions`, `GET /writeups/{id}/diff?from_version=1&to_version=2` e `POST /writeups/{id}/revisions/{revision_id}/restore` mantêm a autorização e criam uma nova revisão ao restaurar.

## Evidências

`POST /evidences` aceita multipart `file`, nome/descrição/origem, `captured_at` ISO com fuso, tags, desafio/equipe e visibilidade privada/equipe. O recebimento é gerado pelo servidor. Downloads, thumbnails, versões e anotações exigem autorização. `POST /evidences/{id}/annotations` recebe `{expected_version,data}` com schema versionado; o original não é sobrescrito.

Associações a documentos usam `/writeups/{id}/evidences`. Os recursos precisam ser visíveis ao usuário e pertencer a workspaces compatíveis. O retorno de associação inclui a nova versão de writeup; o editor deve atualizar sua versão antes do próximo autosave.

## Revisão, entrega e integrações

Solicitações de revisão apontam para usuário revisor e versão do documento. Decisões usam `/reviews/{id}/decision`; o autor não decide sua própria aprovação. Publicação recebe `expected_version`, visibilidade, seleção de evidências e confirmação pública. `/public/writeups/{publication_id}` expõe somente o snapshot autorizado, não o endpoint de edição.

`POST /writeups/{id}/exports` cria exportação real. Consulte `/exports/{id}`, baixe em `/exports/{id}/download` e solicite cancelamento em `/exports/{id}/cancel`. O formato e conteúdo ficam congelados na versão solicitada. Anexos originais exigem opção explícita e permissão apropriada.

IA usa `/ai/providers` e `/ai/jobs`; Kali usa `/kali/status`, `/kali/tools` e `/kali/run`. Ambos são opt-in. Os contratos completos e exemplos específicos estão em [IA](AI.md) e [Kali MCP](KALI-MCP.md).
