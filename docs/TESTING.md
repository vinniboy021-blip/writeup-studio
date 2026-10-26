# Testes e validação

A validação local reproduz a pipeline:

```sh
cd apps/api
python -m pip install -e '.[dev]'
ruff check app tests
pyright
pytest --cov=app --cov-report=term-missing --cov-fail-under=80
```

A suíte de integração usa `TEST_DATABASE_URL` para PostgreSQL e `TEST_REDIS_URL` para Redis. Sem essas variáveis, os testes marcados para infraestrutura são pulados; isso não deve ser interpretado como validação de produção.

Frontend:

```sh
cd apps/web
npm ci
npm run typecheck
npm run lint
npm test -- --run
npm run build
npm run test:e2e
```

O CI executa PostgreSQL/Redis reais, migrations, cobertura mínima de 80%, Ruff, Pyright, build e testes frontend. Docker Compose e Ollama/Kali precisam de um ensaio separado porque dependem do runtime de containers e dos serviços opcionais.

Cada relatório de release deve registrar o comando, o ambiente, a saída e os testes pulados. Não declare uma validação que não foi executada.
