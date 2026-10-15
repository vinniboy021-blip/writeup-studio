# syntax=docker/dockerfile:1
FROM postgres:16.8-bookworm AS pgtools
FROM python:3.12.11-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libmagic1 libpq5 liblz4-1 libzstd1 libssl3 && rm -rf /var/lib/apt/lists/*
COPY --from=pgtools /usr/local/bin/pg_dump /usr/local/bin/pg_restore /usr/local/bin/
COPY apps/api/pyproject.toml ./
COPY apps/api/app ./app
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then PIP_CERT=/run/secrets/proxy_ca pip install --no-cache-dir .; \
    else pip install --no-cache-dir .; fi
COPY apps/api/alembic.ini ./alembic.ini
COPY apps/api/alembic ./alembic
COPY workers ./workers
COPY scripts ./scripts
RUN groupadd --gid 10001 studio && useradd --uid 10001 --gid studio --no-create-home studio && \
    mkdir -p /data/uploads && chown -R studio:studio /data /app
USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--no-server-header"]
