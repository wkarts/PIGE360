#!/bin/sh
set -eu

root="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
mode=""
target=""
environment=""
start=true
skip_migrations=false

usage() {
  printf '%s\n' "Uso: $0 [--environment develop|production] [--mode source|registry] [--target base|cloudpanel|edge|dockge|portainer] [--validate-only] [--skip-migrations]"
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --environment) [ "$#" -ge 2 ] || { usage >&2; exit 2; }; environment="$2"; shift 2 ;;
    --mode) [ "$#" -ge 2 ] || { usage >&2; exit 2; }; mode="$2"; shift 2 ;;
    --target) [ "$#" -ge 2 ] || { usage >&2; exit 2; }; target="$2"; shift 2 ;;
    --validate-only) start=false; shift ;;
    --skip-migrations) skip_migrations=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
  esac
done

PIGE360_ROOT="${PIGE360_ROOT:-$root}"
case "$environment" in
  ''|develop|production) ;;
  *) usage >&2; exit 2 ;;
esac
case "$mode" in
  ''|source|registry) ;;
  *) usage >&2; exit 2 ;;
esac
case "$target" in
  ''|base|cloudpanel|edge|dockge|portainer) ;;
  *) usage >&2; exit 2 ;;
esac

if [ -n "$environment" ]; then
  PIGE360_ENVIRONMENT="$environment"
  export PIGE360_ENVIRONMENT
fi
if [ -n "$mode" ]; then
  PIGE360_IMAGE_MODE="$mode"
  export PIGE360_IMAGE_MODE
fi
if [ -n "$target" ]; then
  PIGE360_DEPLOY_TARGET="$target"
  export PIGE360_DEPLOY_TARGET
fi

if [ -z "${PIGE360_ENV_FILE:-}" ]; then
  if [ -n "$environment" ]; then
    PIGE360_ENV_FILE="$PIGE360_ROOT/.env.$environment"
  else
    PIGE360_ENV_FILE="$PIGE360_ROOT/.env"
  fi
fi
if [ "$skip_migrations" = true ]; then
  PIGE360_SKIP_MIGRATIONS=true
else
  PIGE360_SKIP_MIGRATIONS=false
fi
export PIGE360_ROOT PIGE360_ENV_FILE
export PIGE360_SKIP_MIGRATIONS

mkdir -p "$(dirname -- "$PIGE360_ENV_FILE")"
if [ ! -f "$PIGE360_ENV_FILE" ]; then
  case "$environment" in
    develop|production)
      cp "$PIGE360_ROOT/deploy/env/pige360.$environment.env.example" "$PIGE360_ENV_FILE"
      ;;
    *)
      cp "$PIGE360_ROOT/.env.example" "$PIGE360_ENV_FILE"
      ;;
  esac
  printf '%s\n' "PIGE360: ambiente inicial criado em $PIGE360_ENV_FILE; revise domínios e integrações antes do go-live"
fi

. "$PIGE360_ROOT/deploy/self-hosted/lib.sh"
pige_init_context
sh "$PIGE360_ROOT/scripts/local/init-secrets.sh" "$PIGE360_SECRETS_DIR"
pige_prepare_data_directories
pige_prepare_context
pige_validate_edge_configuration
pige_acquire_operation_lock
trap pige_release_operation_lock EXIT
pige_require_docker
pige_compose config >/dev/null

pige_info "ambiente=$PIGE360_ENVIRONMENT target=$PIGE360_DEPLOY_TARGET mode=$PIGE360_IMAGE_MODE"
pige_info "app-version=$APP_VERSION image-tag=$PIGE360_IMAGE_TAG project=$PIGE360_PROJECT_NAME"
pige_info "env-file=$PIGE360_ENV_FILE secrets=$PIGE360_SECRETS_DIR data=$PIGE360_DATA_ROOT"
case "$PIGE360_DEPLOY_TARGET" in
  edge|dockge|portainer) pige_info "edge-tls=$PIGE360_EDGE_TLS_MODE" ;;
esac

if [ "$start" = false ]; then
  pige_info "configuração Compose validada; nenhum container foi alterado"
  exit 0
fi

if [ "$PIGE360_IMAGE_MODE" = source ]; then
  sh "$PIGE360_ROOT/deploy/self-hosted/build-images.sh"
else
  pige_pull_first_party_images
fi

pige_info "iniciando dependências persistentes"
pige_compose up -d --no-build --wait --wait-timeout "${PIGE360_STARTUP_TIMEOUT_SECONDS:-300}" \
  pige360-postgres-control pige360-postgres-tenants pige360-minio
if [ "$skip_migrations" = false ]; then
  pige_info "subindo o stack; o serviço one-shot pige360-app-init executará Control + tenants"
else
  pige_info "migrations ignoradas; use somente em rollback de aplicação comprovadamente compatível"
fi

pige_compose up -d --no-build --remove-orphans
sh "$PIGE360_ROOT/deploy/self-hosted/healthcheck.sh"
pige_info "instalação concluída (environment=$PIGE360_ENVIRONMENT, target=$PIGE360_DEPLOY_TARGET, mode=$PIGE360_IMAGE_MODE, app=$APP_VERSION, image=$PIGE360_IMAGE_TAG)"
