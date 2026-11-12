# Contribuindo

## Fluxo de trabalho

1. Crie um branch a partir de `main` (`feat/`, `fix/`, `docs/`, `chore/`)
2. Faça alterações focadas — um assunto por PR
3. Execute a suíte local antes de abrir PR (veja abaixo)
4. Abra PR com descrição do problema, solução e evidência de teste
5. Aguarde revisão; push direto em `main` está bloqueado quando branch protection estiver ativo

## Checklist antes de abrir PR

```bash
# Backend
cd apps/api
ruff check app tests
pyright app/security.py app/modules/identity/services.py \
         app/modules/identity/routes.py app/modules/evidence/validation.py
pytest --cov=app --cov-fail-under=80

# Frontend
cd apps/web
npm run typecheck && npm run lint && npm test -- --run && npm run build

# Atualizar OpenAPI se a API mudou
python scripts/export_openapi.py
```

## Regras

- Toda alteração de modelo SQLAlchemy exige migration Alembic
- Novas rotas autenticadas exigem teste de autorização (`test_auth_*`)
- Não inclua segredos, tokens, certificados ou evidências reais
- Commits devem ser claros: `tipo(escopo): descrição em imperativo`
- Não quebre a cobertura de testes abaixo de 80%

## Dependências

- Python: adicione ao `pyproject.toml` e gere `requirements.lock` com `pip-compile`
- Node: use `npm install --save` e faça commit do `package-lock.json` atualizado
- Novas dependências passam por `pip-audit` / `npm audit` no CI

## Licença

Contribuições são aceitas sob MIT. Ao enviar código ou documentação, confirme que possui os direitos necessários para licenciá-los sob MIT.
