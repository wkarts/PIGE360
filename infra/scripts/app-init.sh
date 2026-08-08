#!/bin/sh
set -eu
printf '%s\n' "Inicialização local idempotente do PIGE360"
cd /opt/pige360
python -m alembic -c backend/alembic_control/alembic.ini upgrade head
# O provisionador aplica backend/alembic_tenant/alembic.ini em cada banco dedicado.
python - <<'PY2'
print('Migrations do Control Plane aplicadas; filas/providers permanecem condicionais.')
PY2
