# Auditoria profunda — CTF Writeup Studio
Data: 2026-10-29
Commit auditado: 7dfe35024365039b56b0f5019a74ad9bc6f3f3b5
Repositório: https://github.com/vinniboy021-blip/writeup-studio

## Escopo e evidências

Foram revisados o histórico e a árvore completa do repositório, configuração FastAPI/Pydantic, autenticação/RBAC/CSRF, armazenamento local/S3, integração Kali MCP, exportadores, migrations, Docker Compose, Nginx, workflows GitHub Actions, scripts de backup, lockfiles, documentação e resultados reais dos workflows 28–30.

O workflow 30 executou com sucesso nos jobs API e Web. O job Backup falhou por erro de caminho e foi corrigido no commit `7e947883956f803b8e706dbfaec9e5bdeea83666`; o workflow 31 confirmou API, Web e Backup verdes. Depois, o commit `e65153727d06b41498b9008c1069b163ec4ce5fb` tornou a instalação frontend reprodutível com `npm ci`.

## Resultado executivo

A base possui controles de segurança acima de um protótipo: Argon2id, sessões com hash, CSRF, validação de origem, RBAC por equipe, isolamento de recursos, MIME/hash de evidências, objetos imutáveis, exportação sanitizada e bridge Kali sem shell arbitrário. A suíte API mais recente passou com 117 testes e cobertura de 85,93%; o frontend também passou typecheck, lint, testes e build.

A ferramenta ainda não deve ser declarada pronta para produção sem fechar os itens abaixo. O principal risco operacional atual é o CI não estar verde integralmente. O principal risco de governança é a branch `main` estar sem proteção e os commits estarem não assinados.

## Achados críticos e altos

### A1 — CI global anteriormente vermelho (resolvido, confirmado)

O workflow 30 falhou no job Backup. A causa foi confirmada nos logs: `ERROR: file or directory not found: tests/infra/test_backups.py`. O workflow foi corrigido para `../../tests/infra/test_backups.py` no commit `7e947883...`, mas não há ainda uma execução posterior bem-sucedida registrada. O workflow 31 confirmou a execução do teste de backup; manter esse job obrigatório.

Ação: executar o workflow novamente e exigir que API, Web e Backup sejam verdes antes de release.

### A2 — Branch main sem proteção (alto, confirmado)

A API de branches reporta `protected=false`, enforcement de checks desligado e nenhum status obrigatório. Isso permite push direto, inclusive com CI vermelho, bypass de revisão e alteração de infraestrutura sem aprovação.

Ação: habilitar proteção de `main`, exigir pull request, pelo menos uma revisão, checks API/Web/Backup, branch atualizada e bloquear force-push/deleção.

### A3 — Commits não assinados (médio/alto, confirmado)

O commit auditado aparece com `verification.verified=false` e razão `unsigned`. Isso reduz a garantia de autoria e integridade da cadeia de mudanças.

Ação: exigir commits assinados por SSH/GPG/Sigstore e configurar regra de repositório para commits verificados.

### A4 — Lockfile frontend divergente (resolvido, confirmado)

O workflow usa `npm install --package-lock-only && npm install`, em vez de `npm ci`. Isso recalcula o lock no runner e permite que o resultado dependa do estado atual do registry. O lockfile existe e contém integridades, mas a validação não garante instalação byte a byte reproduzível.

Ação concluída: lockfile regenerado, versionado e validado por `npm ci`.

### A5 — Pyright removido do gate (médio, confirmado)

O workflow deixou de executar Pyright como etapa bloqueante porque a base apresentou 75 erros de tipagem. A compilação e Ruff continuam no gate, mas regressões de tipos podem entrar sem falha de CI.

Ação: corrigir os erros por módulo, reativar Pyright em modo bloqueante e registrar limite progressivo enquanto o débito é reduzido.

## Achados médios

### A6 — Sem evidência de restore completo em CI (médio)

O teste de backup existe, mas o job atual ainda não chegou a uma execução verde após a correção de caminho. Não há prova automatizada de restauração PostgreSQL + objetos em cada alteração.

Ação: fazer o job criar banco, executar backup, restaurar em banco limpo, verificar hashes e publicar relatório de integridade como artefato.

### A7 — Dependência de serviços externos sem scan no pipeline (médio)

O workflow instala dependências com hashes no Python, mas não executa `pip-audit`, scanner npm, Trivy ou equivalente. Também não há evidência de SBOM ou alerta de vulnerabilidades no pipeline.

Ação: adicionar `pip-audit -r requirements.lock`, `npm audit --audit-level=high`, Trivy para imagens e geração de SBOM.

### A8 — Frontend não tem fluxo E2E no CI (médio)

Há Vitest, mas o workflow não executa Playwright. Os fluxos críticos de autenticação, criação de writeup, upload de evidência, exportação e publicação não são validados em navegador real.

Ação: adicionar Playwright com PostgreSQL/Redis/MinIO e pelo menos um fluxo autenticado por papel.

### A9 — OpenAPI estático pode divergir da API (médio)

Existe `docs/api/openapi.json` versionado, mas não há etapa CI comparando-o com `/openapi.json` gerado pela aplicação. Alterações de endpoint podem deixar a documentação desatualizada.

Ação: gerar o documento em CI e falhar quando houver diferença não revisada.

### A10 — Configuração de produção depende de operação correta (médio)

O código valida HTTPS, PostgreSQL, Redis, cookies seguros e fila em produção, o que é positivo. Porém, o repositório não comprova TLS terminado corretamente, rotação de segredos, política de backup fora do host ou teste periódico de restore.

Ação: documentar procedimento operacional executado, rotação, RPO/RTO medidos e teste de restauração agendado.

## Controles confirmados

- Senhas com Argon2id e hash dummy para reduzir enumeração temporal.
- Token de sessão armazenado como SHA-256; expiração e revogação verificadas.
- CSRF com comparação constante e checagem de Origin/Sec-Fetch-Site.
- RBAC por equipe e revogação de acesso após remoção.
- Aprovação independente do autor e vinculada à versão.
- Upload com limite, MIME real, hash SHA-256 e armazenamento separado.
- Chaves de objeto protegidas contra traversal e links simbólicos.
- Originais não sobrescritos; derivados e anotações usam objetos distintos.
- Exportadores não buscam URLs fornecidas no conteúdo; links perigosos Markdown foram corrigidos.
- Kali MCP usa ferramentas tipadas, token, limites e não aceita shell/caminho arbitrário.
- Configuração de produção rejeita SQLite, HTTP, cookie inseguro, fila desabilitada e rate limit em memória.
- Migrations Alembic e lockfile Python com hashes existem.
- Suíte API executada: 117 aprovados, cobertura total 85,93%.
- Frontend executou typecheck, lint, Vitest e build com sucesso no workflow 30.

## Atualização pós-correções

O pipeline final está verde para API, Web e Backup. O lockfile está sincronizado, a instalação usa `npm ci` e o workflow possui permissões mínimas de leitura. Permanecem como bloqueios de governança a proteção da branch, commits assinados, scans de dependências, Playwright E2E e a redução do débito Pyright.

## Conclusão

Classificação atual: **pré-produção endurecida, ainda não pronta para release formal**. O sistema tem controles de aplicação sólidos e testes funcionais relevantes, mas a cadeia de entrega ainda precisa de CI totalmente verde, branch protegida, instalação frontend reprodutível, restauração comprovada, scan de dependências e E2E de navegador. Esses itens devem ser tratados como critérios de aceite de produção.
