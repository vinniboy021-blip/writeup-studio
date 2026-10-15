# syntax=docker/dockerfile:1
FROM node:22.16.0-bookworm-slim AS builder
WORKDIR /app
ARG API_INTERNAL_URL=http://api:8000
ENV NEXT_TELEMETRY_DISABLED=1 API_INTERNAL_URL=$API_INTERNAL_URL
COPY package.json package-lock.json ./
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then NODE_EXTRA_CA_CERTS=/run/secrets/proxy_ca npm ci --strict-ssl=true; \
    else npm ci --strict-ssl=true; fi
COPY . .
RUN npm run build && mkdir -p public

FROM node:22.16.0-bookworm-slim AS runner
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 HOSTNAME=0.0.0.0 PORT=3000
RUN groupadd --gid 10001 studio && useradd --uid 10001 --gid studio --no-create-home studio
COPY --from=builder --chown=studio:studio /app/.next/standalone ./
COPY --from=builder --chown=studio:studio /app/.next/static ./.next/static
COPY --from=builder --chown=studio:studio /app/public ./public
USER 10001:10001
EXPOSE 3000
CMD ["node", "server.js"]
