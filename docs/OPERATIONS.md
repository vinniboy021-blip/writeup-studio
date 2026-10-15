# Operação
pg_dump e cópia do volume uploads formam o backup mínimo. Teste restore periodicamente; RPO/RTO são metas configuráveis. Health check: /api/v1/health; readiness testa a conexão do banco. Logs não incluem conteúdo de evidências.
