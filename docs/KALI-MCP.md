# Integração Kali Linux / Kali MCP

A API aceita um servidor MCP externo configurado por variáveis de ambiente:

- `KALI_ENABLED=true`
- `KALI_MCP_URL=http://host:porta`
- `KALI_MCP_TOKEN` opcional, enviado como Bearer
- `KALI_TIMEOUT_SECONDS=30`

O servidor deve expor `GET /health` e um endpoint JSON-RPC `POST /mcp` compatível com `tools/call`. A aplicação envia a chamada `exec` com `command` e `timeout`.

Por segurança, a integração vem desligada. Cada execução exige autenticação, CSRF e `confirm=true`, é registrada em `audit_logs` e passa por uma allowlist de comandos de coleta/documentação (`whoami`, `id`, `uname`, `file`, `sha256sum`, `strings`, `cat`, `head`, `tail`, `wc`, `ip` e `ss`). Composição shell, redirecionamentos e ferramentas de exploração são bloqueados. O resultado retorna proveniência `kali-mcp` e exige revisão humana antes de entrar em um writeup.

O projeto não inclui uma imagem Kali MCP porque não existe um padrão único de servidor ou imagem oficial confiável. Conecte um servidor MCP mantido pela sua equipe, restrito a uma rede de laboratório autorizada. Não exponha o endpoint à internet pública.

Rotas: `GET /api/v1/kali/status` e `POST /api/v1/kali/run`.

## Contrato JSON

Requisição para execução:

    {
      "command": "sha256sum evidence.txt",
      "evidence_id": "uuid-opcional",
      "confirm": true
    }

Resposta normalizada:

    {
      "command": "sha256sum evidence.txt",
      "result": {"jsonrpc": "2.0", "result": {}},
      "provenance": {"source": "kali-mcp", "review_required": true}
    }

O servidor MCP precisa aceitar uma mensagem JSON-RPC equivalente a:

    {"jsonrpc":"2.0","id":"request-id","method":"tools/call","params":{"name":"exec","arguments":{"command":"...","timeout":30}}}

## Operação recomendada

Execute Kali em uma VM ou container isolado, com rede de laboratório, usuário sem privilégios e diretório de evidências montado como somente leitura quando possível. Restrinja o endpoint MCP por firewall ou rede interna. Rotacione o token e revise os registros de auditoria. O CTF Writeup Studio não considera o resultado do Kali uma descoberta confirmada: o usuário deve registrar origem, horário, contexto e interpretação.

## Falhas e códigos

- 401: sessão ausente ou expirada.
- 403: comando fora da allowlist ou composição shell bloqueada.
- 428: confirmação explícita ausente.
- 502: servidor MCP indisponível ou timeout.
- 503: integração não configurada.
