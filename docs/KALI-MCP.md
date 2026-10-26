# Integração Kali Linux / Kali MCP

A integração é opcional e vem desabilitada. Ela usa um cliente MCP Streamable HTTP configurado por operação:

- `KALI_ENABLED=true`
- `KALI_MCP_URL=https://host-interno/mcp`
- `KALI_MCP_TOKEN` com pelo menos 32 caracteres
- `KALI_ALLOWED_TOOLS` limitado às ferramentas aprovadas
- `KALI_TIMEOUT_SECONDS` e `KALI_MAX_OUTPUT_BYTES`

A API não aceita comandos, caminhos, URLs ou argumentos arbitrários enviados pelo usuário. As únicas ferramentas aceitas são:

| Ferramenta | Entrada | Resultado |
|---|---|---|
| `system_info` | objeto vazio | informações do ambiente de coleta |
| `artifact_hash` | bytes base64 + nome | SHA-256 |
| `artifact_file` | bytes base64 + nome | MIME identificado por `file` |
| `artifact_strings` | bytes base64 + nome | strings imprimíveis |
| `artifact_json_summary` | bytes base64 + nome | tipo, chaves limitadas e contagem |

O fluxo é:

1. O usuário autentica na plataforma e confirma a execução.
2. Para artefatos, o backend lê uma evidência já autorizada e envia os bytes ao MCP.
3. O bridge valida tamanho, base64, nome e schema; executa somente ferramentas fixas com `shell=False`.
4. O resultado é armazenado como nova evidência JSON, com SHA-256, horário de início/fim, ferramenta, evidência de origem e revisão humana obrigatória.

## Protocolo

O servidor deve responder a `initialize`, `notifications/initialized`, `tools/list` e `tools/call` JSON-RPC 2.0. O cabeçalho Bearer é obrigatório no bridge e a versão MCP negociada é preservada no cliente.

Exemplo de chamada:

```json
{"jsonrpc":"2.0","id":"uuid","method":"tools/call","params":{"name":"artifact_hash","arguments":{"artifact_base64":"...","name":"capture.bin"}}}
```

O bridge interno da aplicação está em `app.modules.integrations.kali_bridge`; ele não expõe documentação OpenAPI e exige `KALI_BRIDGE_TOKEN` ou `KALI_MCP_TOKEN` com 32 caracteres. A imagem opcional em `infra/kali/Dockerfile` deve ficar em rede de laboratório isolada.

Não use esta integração para executar exploração arbitrária ou comandos fornecidos por usuários. O resultado é uma observação com proveniência, não uma descoberta automaticamente confirmada.

Rotas da API:

- `GET /api/v1/kali/status`
- `GET /api/v1/kali/tools`
- `POST /api/v1/kali/run`

Códigos comuns: 401 token/sessão inválida, 403 ferramenta ou equipe não autorizada, 428 confirmação ausente, 502 MCP indisponível, 503 integração desligada.
