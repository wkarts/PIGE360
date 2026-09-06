#!/bin/sh
set -eu
printf '%s\n' "Inicialização local idempotente do PIGE360"
cd /opt/pige360
if [ "${PIGE360_SKIP_MIGRATIONS:-false}" = "true" ]; then
  printf '%s\n' 'Todas as migrations foram ignoradas por solicitação explícita.'
else
  python -m alembic -c backend/alembic_control/alembic.ini upgrade head
  if [ "${PIGE360_SKIP_TENANT_MIGRATIONS:-false}" != "true" ]; then
    python -m app.shared.database.migrate_tenants
  else
    printf '%s\n' 'Migrations dos tenants ignoradas por solicitação explícita.'
  fi
  printf '%s\n' 'Migrations do Control Plane e dos tenants elegíveis aplicadas.'
fi
