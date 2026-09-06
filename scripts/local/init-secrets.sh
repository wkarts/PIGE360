#!/bin/sh
set -eu
root="${1:-runtime-secrets}"
umask 077

die() {
  printf '%s\n' "ERRO: $*" >&2
  exit 1
}

# Os arquivos deste diretório são fontes de Docker Compose secrets. O diretório
# 0700 impede que outros usuários do host enumerem ou abram os arquivos. Cada
# arquivo fica 0444 porque o Docker Compose local o materializa como bind mount e
# preserva o modo do arquivo-fonte; desse modo os processos first-party executados
# como UID 10001 conseguem ler /run/secrets sem tornar o diretório acessível no host.
[ ! -L "$root" ] || die "o diretório de segredos não pode ser um link simbólico: $root"
mkdir -p "$root"
[ -d "$root" ] || die "o caminho de segredos não é um diretório: $root"
chmod 0700 "$root"

assert_secret_path() {
  secret_path="$1"
  [ ! -L "$secret_path" ] || die "segredo não pode ser link simbólico: $secret_path"
  [ ! -e "$secret_path" ] || [ -f "$secret_path" ] || \
    die "segredo existente não é arquivo regular: $secret_path"
}

write_generated_secret() {
  secret_path="$1"
  generator="$2"
  assert_secret_path "$secret_path"
  [ ! -s "$secret_path" ] || return 0
  temporary="$root/.secret.$$"
  [ ! -e "$temporary" ] || die "arquivo temporário de segredo já existe: $temporary"
  trap 'rm -f "$temporary"' EXIT HUP INT TERM
  "$generator" > "$temporary"
  [ -s "$temporary" ] || die "gerador produziu segredo vazio: $secret_path"
  chmod 0444 "$temporary"
  mv "$temporary" "$secret_path"
  trap - EXIT HUP INT TERM
}

write_empty_external_secret() {
  secret_path="$1"
  assert_secret_path "$secret_path"
  if [ ! -e "$secret_path" ]; then
    temporary="$root/.secret.$$"
    [ ! -e "$temporary" ] || die "arquivo temporário de segredo já existe: $temporary"
    trap 'rm -f "$temporary"' EXIT HUP INT TERM
    : > "$temporary"
    chmod 0444 "$temporary"
    mv "$temporary" "$secret_path"
    trap - EXIT HUP INT TERM
  fi
}

random_hex() {
  if command -v python3 >/dev/null 2>&1; then
    python3 -c 'import secrets;print(secrets.token_hex(48))'
  elif command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 48
  else
    printf '%s\n' 'python3 ou openssl é obrigatório para gerar segredos.' >&2
    exit 3
  fi
}

fernet_key() {
  if command -v python3 >/dev/null 2>&1; then
    python3 - <<'PY2'
import base64
import secrets
print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii"))
PY2
  elif command -v openssl >/dev/null 2>&1; then
    openssl rand -base64 32 | tr '+/' '-_'
  else
    printf '%s\n' 'python3 ou openssl é obrigatório para gerar a chave Fernet.' >&2
    exit 3
  fi
}

minio_access_key() {
  if command -v python3 >/dev/null 2>&1; then
    suffix="$(python3 -c 'import secrets;print(secrets.token_hex(6))')"
  else
    suffix="$(openssl rand -hex 6)"
  fi
  printf '%s\n' "pige360${suffix}"
}

for name in app_jwt_secret bootstrap_token minio_secret_key postgres_control_password postgres_tenant_password grafana_admin_password redis_password rabbitmq_password worker_context_signing_key build_farm_token; do
  write_generated_secret "$root/$name.txt" random_hex
done

write_generated_secret "$root/database_secret_key.txt" fernet_key
write_generated_secret "$root/minio_access_key.txt" minio_access_key

for name in cloudflare_control_tunnel_token cloudflare_tenant_tunnel_token cloudflare_api_token connect_api_key; do
  write_empty_external_secret "$root/$name.txt"
done

# Normaliza também arquivos preservados de execuções anteriores. A proteção no
# host é dada pelo diretório 0700; o modo 0444 é necessário para os containers
# non-root quando Docker Compose usa secrets baseados em arquivo.
for secret_path in "$root"/*.txt; do
  assert_secret_path "$secret_path"
  chmod 0444 "$secret_path"
done
printf '%s\n' "Segredos locais criados em $root (diretório 0700; arquivos 0444 para Docker secrets non-root). Tokens externos ficaram vazios."
