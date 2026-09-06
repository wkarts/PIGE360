#!/bin/sh

# Biblioteca compartilhada pelos scripts self-hosted. O chamador deve habilitar
# `set -eu` antes de carregar este arquivo.

pige_die() {
  printf '%s\n' "ERRO: $*" >&2
  exit 1
}

pige_info() {
  printf '%s\n' "PIGE360: $*"
}

pige_abspath() {
  pige_path_value="$1"
  case "$pige_path_value" in
    /*) printf '%s\n' "$pige_path_value" ;;
    *) printf '%s/%s\n' "$(pwd -P)" "$pige_path_value" ;;
  esac
}

pige_abspath_from() {
  pige_path_base="$1"
  pige_path_value="$2"
  case "$pige_path_value" in
    /*) printf '%s\n' "$pige_path_value" ;;
    *) printf '%s/%s\n' "$pige_path_base" "$pige_path_value" ;;
  esac
}

pige_env_value() {
  pige_env_key="$1"
  pige_env_file="$2"
  [ -f "$pige_env_file" ] || return 0
  awk -F= -v wanted="$pige_env_key" '
    $0 !~ /^[[:space:]]*#/ && $1 == wanted {
      sub(/^[^=]*=/, ""); sub(/\r$/, ""); print; exit
    }
  ' "$pige_env_file"
}

pige_env_has_key() {
  pige_env_key="$1"
  pige_env_file="$2"
  [ -f "$pige_env_file" ] || return 1
  awk -F= -v wanted="$pige_env_key" '
    $0 !~ /^[[:space:]]*#/ && $1 == wanted { found=1; exit }
    END { exit(found ? 0 : 1) }
  ' "$pige_env_file"
}

# Precedência operacional: variável exportada/CLI > env-file > valor padrão.
# O env-file não é executado como shell; somente pares KEY=VALUE são lidos.
pige_resolve_value() {
  pige_resolve_key="$1"
  pige_resolve_default="${2:-}"
  if pige_resolve_current="$(printenv "$pige_resolve_key" 2>/dev/null)"; then
    printf '%s\n' "$pige_resolve_current"
    return 0
  fi
  if pige_env_has_key "$pige_resolve_key" "$PIGE360_ENV_FILE"; then
    pige_env_value "$pige_resolve_key" "$PIGE360_ENV_FILE"
    return 0
  fi
  printf '%s\n' "$pige_resolve_default"
}

pige_resolve_nonempty() {
  pige_resolve_result="$(pige_resolve_value "$1" "${2:-}")"
  if [ -n "$pige_resolve_result" ]; then
    printf '%s\n' "$pige_resolve_result"
  else
    printf '%s\n' "${2:-}"
  fi
}

pige_validate_safe_name() {
  pige_safe_label="$1"
  pige_safe_value="$2"
  case "$pige_safe_value" in
    ''|*[!A-Za-z0-9_.-]*) pige_die "$pige_safe_label inválido: $pige_safe_value" ;;
  esac
}

pige_init_context() {
  pige_script_root="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
  PIGE360_ROOT="${PIGE360_ROOT:-$pige_script_root}"
  PIGE360_ROOT="$(CDPATH= cd -- "$PIGE360_ROOT" && pwd)"
  PIGE360_ENV_FILE="${PIGE360_ENV_FILE:-$PIGE360_ROOT/.env}"
  PIGE360_ENV_FILE="$(pige_abspath_from "$PIGE360_ROOT" "$PIGE360_ENV_FILE")"
  export PIGE360_ROOT PIGE360_ENV_FILE

  PIGE360_ENVIRONMENT="$(pige_resolve_nonempty PIGE360_ENVIRONMENT production)"
  case "$PIGE360_ENVIRONMENT" in
    develop|production) ;;
    *) pige_die "ambiente inválido: $PIGE360_ENVIRONMENT (use develop ou production)" ;;
  esac

  PIGE360_DEPLOY_TARGET="$(pige_resolve_nonempty PIGE360_DEPLOY_TARGET base)"
  PIGE360_IMAGE_MODE="$(pige_resolve_nonempty PIGE360_IMAGE_MODE source)"
  PIGE360_PROJECT_NAME="$(pige_resolve_nonempty PIGE360_PROJECT_NAME pige360)"
  PIGE360_IMAGE_REGISTRY="$(pige_resolve_value PIGE360_IMAGE_REGISTRY '')"
  PIGE360_IMAGE_TAG="$(pige_resolve_nonempty PIGE360_IMAGE_TAG "$(tr -d '[:space:]' < "$PIGE360_ROOT/VERSION")")"
  APP_VERSION="$(pige_resolve_nonempty APP_VERSION "$(tr -d '[:space:]' < "$PIGE360_ROOT/VERSION")")"

  pige_secrets_value="$(pige_resolve_nonempty PIGE360_SECRETS_DIR "runtime-secrets/$PIGE360_ENVIRONMENT")"
  PIGE360_SECRETS_DIR="$(pige_abspath_from "$PIGE360_ROOT" "$pige_secrets_value")"
  pige_data_value="$(pige_resolve_nonempty PIGE360_DATA_ROOT "volumes/$PIGE360_ENVIRONMENT")"
  PIGE360_DATA_ROOT="$(pige_abspath_from "$PIGE360_ROOT" "$pige_data_value")"
  PIGE360_DATA_MODE="$(pige_resolve_nonempty PIGE360_DATA_MODE named)"

  PIGE360_NETWORK_APP_NAME="$(pige_resolve_nonempty PIGE360_NETWORK_APP_NAME "$PIGE360_PROJECT_NAME-app")"
  PIGE360_NETWORK_DATA_NAME="$(pige_resolve_nonempty PIGE360_NETWORK_DATA_NAME "$PIGE360_PROJECT_NAME-data")"
  PIGE360_NETWORK_OBSERVABILITY_NAME="$(pige_resolve_nonempty PIGE360_NETWORK_OBSERVABILITY_NAME "$PIGE360_PROJECT_NAME-observability")"
  PIGE360_NETWORK_BUILD_FARM_NAME="$(pige_resolve_nonempty PIGE360_NETWORK_BUILD_FARM_NAME "$PIGE360_PROJECT_NAME-build-farm")"

  pige_cloudflare_enabled="$(pige_resolve_nonempty CLOUDFLARE_ENABLED false)"
  case "$pige_cloudflare_enabled" in
    true) pige_default_edge_tls=cloudflare ;;
    false)
      if [ "$PIGE360_ENVIRONMENT" = production ]; then
        pige_default_edge_tls=cloudflare
      else
        pige_default_edge_tls=http
      fi
      ;;
    *) pige_die "CLOUDFLARE_ENABLED deve ser true ou false." ;;
  esac
  PIGE360_EDGE_TLS_MODE="$(pige_resolve_nonempty PIGE360_EDGE_TLS_MODE "$pige_default_edge_tls")"
  PIGE360_ALLOW_INSECURE_HTTP="$(pige_resolve_nonempty PIGE360_ALLOW_INSECURE_HTTP false)"
  PIGE360_STARTUP_TIMEOUT_SECONDS="$(pige_resolve_nonempty PIGE360_STARTUP_TIMEOUT_SECONDS 300)"
  PIGE360_READINESS_ATTEMPTS="$(pige_resolve_nonempty PIGE360_READINESS_ATTEMPTS 30)"
  PIGE360_READINESS_DELAY_SECONDS="$(pige_resolve_nonempty PIGE360_READINESS_DELAY_SECONDS 5)"

  case "$PIGE360_IMAGE_MODE" in
    source|registry) ;;
    *) pige_die "modo de imagem inválido: $PIGE360_IMAGE_MODE (use source ou registry)" ;;
  esac
  case "$PIGE360_DATA_MODE" in
    bind|named) ;;
    *) pige_die "PIGE360_DATA_MODE inválido: $PIGE360_DATA_MODE (use bind ou named)" ;;
  esac
  case "$PIGE360_EDGE_TLS_MODE" in
    cloudflare|http) ;;
    *) pige_die "PIGE360_EDGE_TLS_MODE inválido: $PIGE360_EDGE_TLS_MODE (use cloudflare ou http)" ;;
  esac
  case "$PIGE360_ALLOW_INSECURE_HTTP" in
    true|false) ;;
    *) pige_die "PIGE360_ALLOW_INSECURE_HTTP deve ser true ou false." ;;
  esac
  case "$PIGE360_STARTUP_TIMEOUT_SECONDS:$PIGE360_READINESS_ATTEMPTS:$PIGE360_READINESS_DELAY_SECONDS" in
    *[!0-9:]*) pige_die "timeouts/readiness devem conter inteiros positivos." ;;
  esac
  [ "$PIGE360_STARTUP_TIMEOUT_SECONDS" -gt 0 ] && \
    [ "$PIGE360_READINESS_ATTEMPTS" -gt 0 ] && \
    [ "$PIGE360_READINESS_DELAY_SECONDS" -gt 0 ] || \
    pige_die "timeouts/readiness devem ser maiores que zero."
  case "$PIGE360_IMAGE_TAG" in
    ''|*[!A-Za-z0-9_.-]*) pige_die "PIGE360_IMAGE_TAG inválida: $PIGE360_IMAGE_TAG" ;;
  esac
  printf '%s\n' "$APP_VERSION" | grep -Eq '^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$' || \
    pige_die "APP_VERSION deve ser SemVer estável: $APP_VERSION"
  [ "${#PIGE360_IMAGE_TAG}" -le 128 ] || pige_die "PIGE360_IMAGE_TAG excede 128 caracteres."
  case "$PIGE360_IMAGE_TAG" in
    [A-Za-z0-9_]*) ;;
    *) pige_die "PIGE360_IMAGE_TAG deve iniciar por letra, número ou underscore." ;;
  esac
  case "$PIGE360_IMAGE_REGISTRY" in
    *[!A-Za-z0-9._:/-]*) pige_die "PIGE360_IMAGE_REGISTRY contém caracteres inválidos." ;;
  esac
  [ "$PIGE360_DATA_ROOT" != / ] || pige_die "PIGE360_DATA_ROOT não pode ser /."
  [ "$PIGE360_SECRETS_DIR" != / ] || pige_die "PIGE360_SECRETS_DIR não pode ser /."
  pige_validate_safe_name PIGE360_PROJECT_NAME "$PIGE360_PROJECT_NAME"
  pige_validate_safe_name PIGE360_NETWORK_APP_NAME "$PIGE360_NETWORK_APP_NAME"
  pige_validate_safe_name PIGE360_NETWORK_DATA_NAME "$PIGE360_NETWORK_DATA_NAME"
  pige_validate_safe_name PIGE360_NETWORK_OBSERVABILITY_NAME "$PIGE360_NETWORK_OBSERVABILITY_NAME"
  pige_validate_safe_name PIGE360_NETWORK_BUILD_FARM_NAME "$PIGE360_NETWORK_BUILD_FARM_NAME"

  export PIGE360_ROOT PIGE360_ENV_FILE PIGE360_SECRETS_DIR
  export PIGE360_DATA_ROOT PIGE360_DATA_MODE PIGE360_ENVIRONMENT PIGE360_DEPLOY_TARGET
  export PIGE360_IMAGE_MODE PIGE360_PROJECT_NAME PIGE360_IMAGE_REGISTRY
  export PIGE360_IMAGE_TAG APP_VERSION PIGE360_EDGE_TLS_MODE PIGE360_ALLOW_INSECURE_HTTP
  export PIGE360_STARTUP_TIMEOUT_SECONDS PIGE360_READINESS_ATTEMPTS PIGE360_READINESS_DELAY_SECONDS
  export PIGE360_NETWORK_APP_NAME PIGE360_NETWORK_DATA_NAME
  export PIGE360_NETWORK_OBSERVABILITY_NAME PIGE360_NETWORK_BUILD_FARM_NAME
}

pige_validate_target() {
  case "$PIGE360_DEPLOY_TARGET" in
    base|cloudpanel|edge|dockge|portainer) ;;
    *) pige_die "target inválido: $PIGE360_DEPLOY_TARGET (use base, cloudpanel, edge, dockge ou portainer)" ;;
  esac
}

pige_require_docker() {
  command -v docker >/dev/null 2>&1 || pige_die "Docker Engine é obrigatório."
  docker compose version >/dev/null 2>&1 || pige_die "Docker Compose v2 é obrigatório."
}

pige_configure_images() {
  case "$PIGE360_IMAGE_MODE" in
    source)
      pige_image_prefix=""
      PIGE360_PULL_POLICY=never
      ;;
    registry)
      [ -n "$PIGE360_IMAGE_REGISTRY" ] || pige_die "PIGE360_IMAGE_REGISTRY é obrigatório no modo registry."
      pige_image_prefix="${PIGE360_IMAGE_REGISTRY%/}/"
      PIGE360_PULL_POLICY=always
      ;;
  esac

  pige_api_default="${pige_image_prefix}pige360-api:${PIGE360_IMAGE_TAG}"
  pige_migrations_default="${pige_image_prefix}pige360-migrations:${PIGE360_IMAGE_TAG}"
  pige_worker_default="${pige_image_prefix}pige360-worker:${PIGE360_IMAGE_TAG}"
  pige_web_default="${pige_image_prefix}pige360-web:${PIGE360_IMAGE_TAG}"
  pige_console_default="${pige_image_prefix}pige360-platform-console:${PIGE360_IMAGE_TAG}"
  pige_branding_default="${pige_image_prefix}pige360-branding-studio:${PIGE360_IMAGE_TAG}"
  pige_download_default="${pige_image_prefix}pige360-tenant-download-center:${PIGE360_IMAGE_TAG}"
  if [ "$PIGE360_IMAGE_MODE" = registry ]; then
    PIGE360_API_IMAGE="$(pige_resolve_nonempty PIGE360_API_IMAGE "$pige_api_default")"
    PIGE360_MIGRATIONS_IMAGE="$(pige_resolve_nonempty PIGE360_MIGRATIONS_IMAGE "$pige_migrations_default")"
    PIGE360_WORKER_IMAGE="$(pige_resolve_nonempty PIGE360_WORKER_IMAGE "$pige_worker_default")"
    PIGE360_WEB_IMAGE="$(pige_resolve_nonempty PIGE360_WEB_IMAGE "$pige_web_default")"
    PIGE360_PLATFORM_CONSOLE_IMAGE="$(pige_resolve_nonempty PIGE360_PLATFORM_CONSOLE_IMAGE "$pige_console_default")"
    PIGE360_BRANDING_STUDIO_IMAGE="$(pige_resolve_nonempty PIGE360_BRANDING_STUDIO_IMAGE "$pige_branding_default")"
    PIGE360_TENANT_DOWNLOAD_CENTER_IMAGE="$(pige_resolve_nonempty PIGE360_TENANT_DOWNLOAD_CENTER_IMAGE "$pige_download_default")"
  else
    PIGE360_API_IMAGE="$pige_api_default"
    PIGE360_MIGRATIONS_IMAGE="$pige_migrations_default"
    PIGE360_WORKER_IMAGE="$pige_worker_default"
    PIGE360_WEB_IMAGE="$pige_web_default"
    PIGE360_PLATFORM_CONSOLE_IMAGE="$pige_console_default"
    PIGE360_BRANDING_STUDIO_IMAGE="$pige_branding_default"
    PIGE360_TENANT_DOWNLOAD_CENTER_IMAGE="$pige_download_default"
  fi
  PIGE360_APP_FACTORY_IMAGE="$PIGE360_API_IMAGE"
  export PIGE360_PULL_POLICY PIGE360_API_IMAGE
  export PIGE360_MIGRATIONS_IMAGE PIGE360_WORKER_IMAGE PIGE360_WEB_IMAGE
  export PIGE360_PLATFORM_CONSOLE_IMAGE PIGE360_BRANDING_STUDIO_IMAGE
  export PIGE360_TENANT_DOWNLOAD_CENTER_IMAGE PIGE360_APP_FACTORY_IMAGE
}

pige_is_stable_semver() {
  printf '%s\n' "$1" | grep -Eq '^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$'
}

pige_is_digest_reference() {
  printf '%s\n' "$1" | grep -Eq '@sha256:[0-9a-f]{64}$'
}

pige_image_reference_tag() {
  # O nome pode conter porta no registry; somente o sufixo depois do ultimo ':'
  # e considerado tag. Referencias por digest sao tratadas separadamente.
  printf '%s\n' "${1##*:}"
}

pige_validate_image_channel() {
  # A variavel do pipeline precisa apontar para um canal coerente. Quando todas
  # as imagens sao referencias imutaveis por digest, a tag nao participa do pull.
  pige_all_refs_pinned=true
  for pige_image in \
    "$PIGE360_MIGRATIONS_IMAGE" "$PIGE360_API_IMAGE" "$PIGE360_WORKER_IMAGE" \
    "$PIGE360_WEB_IMAGE" "$PIGE360_PLATFORM_CONSOLE_IMAGE" \
    "$PIGE360_BRANDING_STUDIO_IMAGE" "$PIGE360_TENANT_DOWNLOAD_CENTER_IMAGE"; do
    if ! pige_is_digest_reference "$pige_image"; then
      pige_all_refs_pinned=false
      break
    fi
  done

  if [ "$PIGE360_ENVIRONMENT" = production ]; then
    if [ "$pige_all_refs_pinned" != true ] && ! pige_is_stable_semver "$PIGE360_IMAGE_TAG"; then
      pige_die "produção exige PIGE360_IMAGE_TAG SemVer estável (X.Y.Z) ou todas as PIGE360_*_IMAGE fixadas por sha256; recebido: $PIGE360_IMAGE_TAG"
    fi
    for pige_image in \
      "$PIGE360_MIGRATIONS_IMAGE" "$PIGE360_API_IMAGE" "$PIGE360_WORKER_IMAGE" \
      "$PIGE360_WEB_IMAGE" "$PIGE360_PLATFORM_CONSOLE_IMAGE" \
      "$PIGE360_BRANDING_STUDIO_IMAGE" "$PIGE360_TENANT_DOWNLOAD_CENTER_IMAGE"; do
      pige_is_digest_reference "$pige_image" && continue
      pige_image_tag="$(pige_image_reference_tag "$pige_image")"
      pige_is_stable_semver "$pige_image_tag" || \
        pige_die "produção recusou imagem não imutável/estável: $pige_image"
    done
    return 0
  fi

  case "$PIGE360_IMAGE_TAG" in
    develop) pige_channel_ok=true ;;
    develop-*)
      printf '%s\n' "$PIGE360_IMAGE_TAG" | grep -Eq '^develop-[0-9a-f]{7,64}$' && \
        pige_channel_ok=true || pige_channel_ok=false
      ;;
    *)
      pige_is_stable_semver "$PIGE360_IMAGE_TAG" && pige_channel_ok=true || pige_channel_ok=false
      ;;
  esac
  if [ "$pige_channel_ok" != true ] && [ "$pige_all_refs_pinned" != true ]; then
    pige_die "develop aceita somente develop, develop-<sha>, SemVer estável ou todas as imagens fixadas por sha256; recebido: $PIGE360_IMAGE_TAG"
  fi
  for pige_image in \
    "$PIGE360_MIGRATIONS_IMAGE" "$PIGE360_API_IMAGE" "$PIGE360_WORKER_IMAGE" \
    "$PIGE360_WEB_IMAGE" "$PIGE360_PLATFORM_CONSOLE_IMAGE" \
    "$PIGE360_BRANDING_STUDIO_IMAGE" "$PIGE360_TENANT_DOWNLOAD_CENTER_IMAGE"; do
    pige_is_digest_reference "$pige_image" && continue
    pige_image_tag="$(pige_image_reference_tag "$pige_image")"
    case "$pige_image_tag" in
      develop) continue ;;
      develop-*)
        printf '%s\n' "$pige_image_tag" | grep -Eq '^develop-[0-9a-f]{7,64}$' && continue
        ;;
    esac
    pige_is_stable_semver "$pige_image_tag" || \
      pige_die "develop recusou canal de imagem inválido: $pige_image"
  done
}

pige_prepare_data_directories() {
  [ "$PIGE360_DATA_MODE" = bind ] || return 0
  mkdir -p "$PIGE360_DATA_ROOT"
  for pige_data_dir in \
    postgres-control postgres-tenants redis rabbitmq minio clamav tenant-storage \
    prometheus grafana loki traefik-acme traefik-dynamic; do
    mkdir -p "$PIGE360_DATA_ROOT/$pige_data_dir"
    chmod 0750 "$PIGE360_DATA_ROOT/$pige_data_dir"
  done
  chmod 0750 "$PIGE360_DATA_ROOT"
}

pige_validate_edge_configuration() {
  case "$PIGE360_DEPLOY_TARGET" in
    edge|dockge|portainer) ;;
    *) return 0 ;;
  esac
  case "$PIGE360_EDGE_TLS_MODE" in
    cloudflare)
      [ -s "$PIGE360_SECRETS_DIR/cloudflare_api_token.txt" ] || \
        pige_die "TLS Cloudflare exige $PIGE360_SECRETS_DIR/cloudflare_api_token.txt preenchido."
      pige_acme_email="$(pige_resolve_value ACME_EMAIL '')"
      case "$pige_acme_email" in
        *@*.*) ;;
        *) pige_die "ACME_EMAIL válido é obrigatório para TLS Cloudflare." ;;
      esac
      ;;
    http)
      if [ "$PIGE360_ENVIRONMENT" = production ] && [ "$PIGE360_ALLOW_INSECURE_HTTP" != true ]; then
        pige_die "edge HTTP em produção foi recusado; use CloudPanel/TLS Cloudflare ou confirme PIGE360_ALLOW_INSECURE_HTTP=true atrás de proxy TLS."
      fi
      ;;
  esac
}

pige_first_party_images() {
  printf '%s\n' \
    "$PIGE360_MIGRATIONS_IMAGE" \
    "$PIGE360_API_IMAGE" \
    "$PIGE360_WORKER_IMAGE" \
    "$PIGE360_WEB_IMAGE" \
    "$PIGE360_PLATFORM_CONSOLE_IMAGE" \
    "$PIGE360_BRANDING_STUDIO_IMAGE" \
    "$PIGE360_TENANT_DOWNLOAD_CENTER_IMAGE"
}

pige_pull_first_party_images() {
  [ "$PIGE360_IMAGE_MODE" = registry ] || pige_die "pull first-party exige modo registry."
  pige_info "baixando imagens first-party do canal $PIGE360_IMAGE_TAG"
  pige_first_party_images | while IFS= read -r pige_image; do
    [ -n "$pige_image" ] || continue
    pige_info "pull $pige_image"
    docker pull "$pige_image"
    docker image inspect "$pige_image" >/dev/null
  done
}

pige_acquire_operation_lock() {
  if [ -n "${PIGE360_OPERATION_LOCK_TOKEN:-}" ]; then
    [ -f "${PIGE360_OPERATION_LOCK_PATH:-}/owner" ] || pige_die "lock herdado não existe."
    [ "$(cat "$PIGE360_OPERATION_LOCK_PATH/owner")" = "$PIGE360_OPERATION_LOCK_TOKEN" ] || \
      pige_die "lock herdado não pertence a esta operação."
    return 0
  fi
  pige_lock_root="${PIGE360_STATE_DIR:-$(dirname -- "$PIGE360_ENV_FILE")/.pige360-state}/locks"
  PIGE360_OPERATION_LOCK_PATH="$pige_lock_root/deployment.lock"
  mkdir -p "$pige_lock_root"
  if ! mkdir "$PIGE360_OPERATION_LOCK_PATH" 2>/dev/null; then
    pige_die "outra operação de instalação/backup/update/restore está em execução: $PIGE360_OPERATION_LOCK_PATH"
  fi
  PIGE360_OPERATION_LOCK_TOKEN="$$-$(date -u +%Y%m%dT%H%M%SZ)"
  printf '%s\n' "$PIGE360_OPERATION_LOCK_TOKEN" > "$PIGE360_OPERATION_LOCK_PATH/owner"
  PIGE360_OPERATION_LOCK_OWNED=true
  export PIGE360_OPERATION_LOCK_PATH PIGE360_OPERATION_LOCK_TOKEN
}

pige_release_operation_lock() {
  [ "${PIGE360_OPERATION_LOCK_OWNED:-false}" = true ] || return 0
  if [ -f "$PIGE360_OPERATION_LOCK_PATH/owner" ] && \
     [ "$(cat "$PIGE360_OPERATION_LOCK_PATH/owner")" = "$PIGE360_OPERATION_LOCK_TOKEN" ]; then
    rm -f "$PIGE360_OPERATION_LOCK_PATH/owner"
    rmdir "$PIGE360_OPERATION_LOCK_PATH" 2>/dev/null || true
  fi
  PIGE360_OPERATION_LOCK_OWNED=false
}

pige_compose() {
  pige_validate_target
  pige_compose_files="$PIGE360_ROOT/compose.yaml"
  case "$PIGE360_ENVIRONMENT" in
    develop) pige_compose_files="$pige_compose_files:$PIGE360_ROOT/compose.develop.yaml" ;;
    production) pige_compose_files="$pige_compose_files:$PIGE360_ROOT/compose.production.yaml" ;;
  esac
  pige_compose_files="$pige_compose_files:$PIGE360_ROOT/deploy/self-hosted/compose.runtime.yaml"
  case "$PIGE360_DEPLOY_TARGET" in
    base) ;;
    cloudpanel)
      pige_compose_files="$pige_compose_files:$PIGE360_ROOT/deploy/compose/compose.cloudpanel.yaml"
      pige_compose_files="$pige_compose_files:$PIGE360_ROOT/deploy/compose/compose.logging.yaml"
      ;;
    edge|dockge|portainer)
      if [ "$PIGE360_EDGE_TLS_MODE" = cloudflare ]; then
        pige_compose_files="$pige_compose_files:$PIGE360_ROOT/deploy/compose/compose.edge.yaml"
      else
        pige_compose_files="$pige_compose_files:$PIGE360_ROOT/deploy/self-hosted/compose.edge-http.yaml"
      fi
      pige_compose_files="$pige_compose_files:$PIGE360_ROOT/deploy/compose/compose.logging.yaml"
      ;;
  esac
  pige_compose_files="$pige_compose_files:$PIGE360_ROOT/deploy/self-hosted/compose.networks.yaml"
  if [ "$PIGE360_DATA_MODE" = bind ]; then
    pige_compose_files="$pige_compose_files:$PIGE360_ROOT/deploy/self-hosted/compose.data.yaml"
    case "$PIGE360_DEPLOY_TARGET" in
      edge|dockge|portainer)
        pige_compose_files="$pige_compose_files:$PIGE360_ROOT/deploy/self-hosted/compose.edge-data.yaml"
        ;;
    esac
  fi
  COMPOSE_FILE="$pige_compose_files" COMPOSE_PATH_SEPARATOR=: \
    docker compose --project-name "$PIGE360_PROJECT_NAME" --project-directory "$PIGE360_ROOT" \
      --env-file "$PIGE360_ENV_FILE" "$@"
}

pige_prepare_context() {
  pige_init_context
  [ -f "$PIGE360_ENV_FILE" ] || pige_die "arquivo de ambiente ausente: $PIGE360_ENV_FILE"
  [ -d "$PIGE360_SECRETS_DIR" ] || pige_die "diretório de segredos ausente: $PIGE360_SECRETS_DIR"
  pige_configure_images
  pige_validate_image_channel
}
