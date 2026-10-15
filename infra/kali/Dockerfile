# syntax=docker/dockerfile:1
# Kali rolling is upstream's rolling distribution; releases record its resolved digest.
FROM kalilinux/kali-rolling
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv file binutils \
    coreutils ca-certificates && rm -rf /var/lib/apt/lists/*
RUN python3 -m venv /opt/bridge
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then PIP_CERT=/run/secrets/proxy_ca /opt/bridge/bin/pip install --no-cache-dir 'fastapi>=0.115,<1' 'uvicorn>=0.30,<1'; \
    else /opt/bridge/bin/pip install --no-cache-dir 'fastapi>=0.115,<1' 'uvicorn>=0.30,<1'; fi
COPY apps/api/app/__init__.py /app/app/__init__.py
COPY apps/api/app/modules/__init__.py /app/app/modules/__init__.py
COPY apps/api/app/modules/integrations/__init__.py /app/app/modules/integrations/__init__.py
COPY apps/api/app/modules/integrations/kali_bridge.py /app/app/modules/integrations/kali_bridge.py
RUN groupadd --gid 10001 studio && useradd --uid 10001 --gid studio --no-create-home studio
USER 10001:10001
EXPOSE 8080
CMD ["/opt/bridge/bin/python", "-m", "uvicorn", "app.modules.integrations.kali_bridge:app", "--host", "0.0.0.0", "--port", "8080", "--no-access-log", "--no-server-header"]
