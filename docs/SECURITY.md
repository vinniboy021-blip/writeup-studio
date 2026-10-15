# Segurança

## Identidade e sessões

Senhas usam Argon2id sem fallback. O banco guarda hash do token de sessão; o cookie é HttpOnly, SameSite=Lax e Secure obrigatório em produção. Sessões expiram e podem ser revogadas. Mutações autenticadas exigem token CSRF e origem permitida. CORS usa origens explícitas; registro e login têm rate limiting, com Redis obrigatório em produção. Segredos fracos e configuração de produção com SQLite/HTTP/cookie inseguro são rejeitados.

## Papéis e escopo

| Papel | Acesso típico na equipe |
|---|---|
| Administrador global | Administração, sujeito às regras de aprovação independente |
| Gestor | Membros/convites e conteúdo da equipe |
| Editor | Criar e editar conteúdo, comentar e solicitar revisão |
| Revisor | Ler, comentar e decidir revisões atribuídas |
| Visualizador | Ler e exportar recursos autorizados |

Recursos privados exigem proprietário ou administrador. Recursos de equipe exigem membership atual e ação permitida. Remover alguém da equipe retira seu acesso aos recursos compartilhados, inclusive exports/downloads. O autor não aprova seu próprio writeup; a aprovação aponta para versão específica e fica obsoleta após alteração. Consultar históricos, comentários ou metadados também exige autorização.

## Evidências e documentos

Uploads têm extensão permitida, MIME real, validação de estrutura quando aplicável, tamanho limitado, hash SHA-256 e chaves UUID. Imagens passam por Pillow com limites; GIF é preservado como original e recebe preview estático. Arquivos compactados são desabilitados por padrão, sujeitos a política de tamanho/entradas e nunca extraídos automaticamente. O navegador recebe downloads autenticados; conteúdo ativo não é servido como HTML executável.

O original é criado sem sobrescrita. Anotações e thumbnails usam objetos separados. Redação/desfoque altera somente a versão derivada; um original sensível continua protegido. Conteúdo Markdown não permite HTML arbitrário no preview/export HTML. PDF recebe texto escapado e bytes de imagens autorizadas; o renderer não busca URLs ou arquivos descritos pelo usuário.

## Publicação e exportação

Publicação usa snapshot de uma revisão aprovada, com confirmação explícita para público. Originais privados não ganham URL pública. Imagens públicas exigem seleção autorizada de versão derivada e são copiadas para snapshot separado. URLs públicas devem ser tratadas como divulgação real; a operação pode expirar/revogar snapshots. Exportar anexos originais exige opção explícita e proprietário/admin.

## Integrações

Endpoints Ollama, S3 e MCP são configurados pela operação; usuários finais não podem escolher destinos de rede. IA externa exige consentimento. O bridge Kali usa ferramentas tipadas, bytes de evidências autorizadas e `shell=False`, sem caminhos arbitrários. MCP e IA podem transportar dados privados para os destinos configurados; restrinja credenciais e redes de acordo com a implantação.

## Operação

Use TLS, secrets fora do Git, backups protegidos e versões atualizadas das dependências. Logs incluem IDs/tipos/tempos, sem cookies, senhas, tokens ou texto de evidências. Auditoria registra mudanças críticas sem replicar documentos privados. Prometheus/Grafana devem ficar em rede operacional privada. Consulte [a política de divulgação](../SECURITY.md) e o registro de [validação](VALIDATION.md).
