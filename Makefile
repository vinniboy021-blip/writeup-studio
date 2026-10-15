dev:
	docker compose up --build
test:
	python -m pytest apps/api/tests
lint:
	python -m compileall apps/api/app
backup:
	mkdir -p backups
	pg_dump "$$(DATABASE_URL)" > backups/ctf-$$(date -u +%Y%m%dT%H%M%SZ).sql
