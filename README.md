# CTF Writeup Studio

Workspace open source para organizar competições e desafios de CTF, produzir writeups versionados, preservar evidências e colaborar em relatórios técnicos. Backend FastAPI, frontend Next.js, PostgreSQL, Redis/RQ e armazenamento S3/MinIO privado. A IA e o Kali MCP são opcionais: o fluxo de documentação funciona sem credenciais comerciais.

## Instalar

O repositório fornece configuração local e de produção. Use o script de preparação descrito em [docs/INSTALLATION.md](docs/INSTALLATION.md) para gerar o arquivo de ambiente com segredos aleatórios. As configurações de exemplo não devem ser usadas como credenciais de produção.

```sh
python scripts/setup.py
docker compose up --build
```

A interface e a API são servidas pelo proxy na mesma origem. Para desenvolvimento sem Docker, execute migrations antes de iniciar a API e configure o endereço interno do backend no frontend, conforme o guia de instalação.

## Recursos

- Sessões HttpOnly, senhas Argon2id, CSRF e papéis por equipe verificados no backend.
- Competições, desafios, categorias, responsáveis, templates versionados e pesquisa paginada.
- Documento canônico v1 com seções editáveis, autosave, revisões, comparação e restauração. Atualizações usam comparação atômica de versão; um conflito retorna HTTP 409.
- Upload com tamanho limitado, MIME real, SHA-256, metadados e horário de captura declarado separado do recebimento. Downloads e thumbnails exigem autorização.
- Anotações editáveis e imagens derivadas separadas do original; timeline das alterações.
- Comentários, convites, notificações, revisão por outro usuário e publicação de snapshots autorizados.
- Exportação Markdown, HTML, JSON e PDF offline, com índice, tabelas, código e evidências incluídas por opção explícita.
- Jobs RQ com estados e cancelamento; assistência opcional via Ollama e provedor externo configurado com consentimento explícito.
- Bridge Kali MCP para operações de coleta sobre evidências autorizadas, sem shell arbitrário, com resultado armazenado como nova evidência.

## Documentação e validação

Consulte [docs/INDEX.md](docs/INDEX.md). [docs/VALIDATION.md](docs/VALIDATION.md) registra os testes realmente executados e os limites de verificação do ambiente; presença de Dockerfiles ou testes no código não comprova implantação.

```sh
cd apps/api
pip install -e '.[dev]'
pytest
ruff check app tests
```

O frontend tem comandos próprios de type checking, testes, lint e build em `apps/web/package.json`. A CI valida os fluxos com serviços PostgreSQL/Redis e mantém as integrações opcionais isoladas dos testes essenciais.

## Licença

O código próprio é [MIT](LICENSE). PostgreSQL, Redis, MinIO, Kali e demais dependências mantêm suas licenças próprias. Evidências e documentos enviados por usuários não são relicenciados pelo software. Leia [CONTRIBUTING.md](CONTRIBUTING.md) e [SECURITY.md](SECURITY.md).
