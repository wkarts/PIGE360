#!/bin/sh
set -eu
root="${1:-runtime-secrets}"
umask 077
mkdir -p "$root"
random_hex() { python3 -c 'import secrets;print(secrets.token_hex(48))'; }
for name in app_jwt_secret bootstrap_token minio_secret_key postgres_control_password postgres_tenant_password grafana_admin_password redis_password rabbitmq_password worker_context_signing_key build_farm_token; do
  [ -s "$root/$name.txt" ] || random_hex > "$root/$name.txt"
done

[ -s "$root/database_secret_key.txt" ] || python3 - <<'PY2' > "$root/database_secret_key.txt"
from cryptography.fernet import Fernet
print(Fernet.generate_key().decode())
PY2
[ -s "$root/minio_access_key.txt" ] || printf '%s
' "pige360$(python3 -c 'import secrets;print(secrets.token_hex(6))')" > "$root/minio_access_key.txt"
for name in cloudflare_control_tunnel_token cloudflare_tenant_tunnel_token; do
  [ -e "$root/$name.txt" ] || : > "$root/$name.txt"
done
chmod 600 "$root"/*.txt
printf 'Segredos locais criados em %s. Tokens externos ficaram vazios.
' "$root"
