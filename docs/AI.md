# Assistência de IA

A plataforma não exige IA. `AI_ENABLED=false` mantém criação, edição, upload, colaboração e exportação disponíveis.

## Ollama

Configure `OLLAMA_URL` e `OLLAMA_MODEL`, disponibilize o modelo no servidor Ollama e habilite IA. A aplicação usa `/api/chat`, sem streaming, com timeout e formato JSON esperado. O download de um modelo é uma operação explícita da infraestrutura; registrar um provedor não instala pesos de modelo.

```sh
ollama pull llama3.2:3b
```

Em Docker, use o hostname do serviço; não use o localhost do navegador ou da API para outro container. Jobs podem estruturar notas, organizar logs, explicar comandos existentes, resumir fontes, identificar lacunas e melhorar redação. O campo `task` escolhe o pedido de documentação; nenhum job executa comandos do documento.

## Fontes e proveniência

O servidor autoriza cada writeup/evidência antes de ler seu conteúdo. Texto, JSON e CSV pequenos podem fornecer trechos via recuperação lexical de chunks; evidências binárias fornecem metadados/descrição, sem fingir que pixels ou PCAP foram analisados por um modelo de texto.

O resultado contém:

- `facts`: trechos copiados das fontes fornecidas e classificados como observações submetidas pelo usuário;
- `inferences`: hipóteses/sugestões do modelo;
- `gaps`: lacunas identificadas;
- `draft`: rascunho não verificado;
- `provenance`: identificadores, versões e hashes das fontes;
- `human_review_required`: sempre verdadeiro.

Fontes são dados não confiáveis; o prompt instrui o modelo a não seguir instruções embutidas nelas. A saída do modelo continua exigindo revisão humana. A plataforma não pode garantir que um modelo nunca produzirá uma afirmação incorreta; ela mantém a diferença entre fontes observadas e sugestões e não publica a saída automaticamente.

## Provedores externos

Exigem `AI_EXTERNAL_ENABLED`, URL/modelo/token configurados pela operação e `external_consent=true` no job. A interface deve deixar claro que as fontes selecionadas serão enviadas. Tokens não entram em respostas, snapshots de configuração ou auditoria. Não habilite o provedor externo como alternativa silenciosa quando Ollama falhar.

## Estados e limites

`queued → running → completed|failed|cancelled`. O banco persiste os estados; Redis/RQ executa em produção. Há limite de contexto, quota por usuário, timeout e retentativas controladas. Cancelamento solicita interrupção e descarta resultados quando o provedor termina; não promete cancelar uma requisição já processada por um servidor externo. Sem fila, desenvolvimento executa o mesmo código de forma síncrona.
