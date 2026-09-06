#!/usr/bin/env python3
"""Renderiza deployments standalone e image-only do PIGE360.

O Compose de desenvolvimento do repositório continua sendo a fonte funcional dos
serviços. Este gerador cria uma distribuição operacional sem ``build``, anchors,
volumes nomeados ou dependência de caminhos externos ao diretório do deployment.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[2]
DEPLOYMENTS = ROOT / "deployments"

ENVIRONMENTS: dict[str, dict[str, str]] = {
    "develop": {
        "app_env": "staging",
        "version": "1.1.2",
        "tag": "develop",
        "project": "pige360-develop",
        "base_domain": "pige360.argws.com.br",
        "gateway_port": "48080",
        "description": "homologação alimentada pelo canal develop do GHCR",
    },
    "production": {
        "app_env": "production",
        "version": "1.1.2",
        "tag": "1.1.2",
        "project": "pige360-production",
        "base_domain": "pige360.com.br",
        "gateway_port": "58080",
        "description": "produção alimentada por tag SemVer imutável do GHCR",
    },
}

FIRST_PARTY_IMAGES = {
    "pige360-app-init": "pige360-migrations",
    "pige360-api": "pige360-api",
    "pige360-web": "pige360-web",
    "pige360-platform-console": "pige360-platform-console",
    "pige360-branding-studio": "pige360-branding-studio",
    "pige360-tenant-download-center": "pige360-tenant-download-center",
    "pige360-app-factory-api": "pige360-api",
    "pige360-beat": "pige360-worker",
    "pige360-builder-linux": "pige360-builder-linux",
    "pige360-builder-android": "pige360-builder-android",
}

VOLUME_PATHS = {
    "pige360-control-db": "postgres-control",
    "pige360-tenant-dbs": "postgres-tenants",
    "pige360-redis": "redis",
    "pige360-rabbitmq": "rabbitmq",
    "pige360-minio": "minio",
    "pige360-clamav": "clamav",
    "pige360-tenant-storage": "tenant-storage",
    "pige360-prometheus": "prometheus",
    "pige360-grafana": "grafana",
    "pige360-loki": "loki",
}

CONFIG_MOUNTS = {
    "./infra/scripts/init-minio.sh": "./config/init-minio.sh",
    "./infra/monitoring/otel-collector.yaml": "./config/observability/otel-collector.yaml",
    "./infra/monitoring/prometheus.yml": "./config/observability/prometheus.yml",
    "./infra/monitoring/grafana/provisioning": "./config/observability/grafana/provisioning",
    "./infra/monitoring/grafana/dashboards": "./config/observability/grafana/dashboards",
    "./infra/monitoring/loki.yaml": "./config/observability/loki.yaml",
    "./deploy/observability/alloy.config": "./config/observability/alloy.config",
    ".": "./volumes/build-source",
}

APP_CONFIG_KEYS = (
    "APP_ACCESS_TOKEN_MINUTES",
    "APP_CONTROL_DB_PATH",
    "APP_DATA_ROOT",
    "APP_DEMO_MODE",
    "APP_LOGIN_LOCKOUT_MINUTES",
    "APP_LOGIN_MAX_ATTEMPTS",
    "APP_REFRESH_TOKEN_DAYS",
    "APP_STORAGE_ROOT",
    "CLOUDFLARE_SAAS_ENABLED",
    "CLOUDFLARE_TENANT_ZONE_ID",
    "CONNECT_API_BASE_URL",
    "CONNECT_API_ENABLED",
    "CONNECT_API_META_COMPATIBLE",
    "CORS_ALLOWED_ORIGINS",
    "DATABASE_MAX_OVERFLOW",
    "DATABASE_POOL_SIZE",
    "IBPT_API_BASE_URL",
    "IBPT_API_UF_PATH",
    "IBPT_PROVIDER",
    "IBPT_SYNC_ENABLED",
    "IMAP_HOST",
    "IMAP_PORT",
    "INTEGRATION_REMOTE_ENABLED",
    "LOKI_INTERNAL_URL",
    "MAIL_MODE",
    "MINIO_REGION",
    "MINIO_SECURE",
    "NOTIFICATION_SCHEDULER_INTERVAL_SECONDS",
    "OUTBOX_PUBLISH_INTERVAL_SECONDS",
    "READINESS_REQUIRE_OBJECT_STORAGE",
    "READINESS_REQUIRE_RABBITMQ",
    "READINESS_REQUIRE_REDIS",
    "READINESS_TIMEOUT_SECONDS",
    "SIGNATURE_INTERNAL_OTP_REQUIRED",
    "SIGNATURE_OTP_MAX_ATTEMPTS",
    "SIGNATURE_OTP_TTL_SECONDS",
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_TLS",
    "TENANT_BRAND_ASSET_MAX_MB",
    "TENANT_CUSTOM_DOMAIN_CNAME_TARGET",
    "TENANT_RESERVED_SLUGS",
    "TRUSTED_PROXY_CIDRS",
    "WORKFLOW_SLA_INTERVAL_SECONDS",
)

GENERATED_MODES = {
    "install.sh": 0o755,
    "validate.sh": 0o755,
    "healthcheck.sh": 0o755,
    "logs.sh": 0o755,
    "stop.sh": 0o755,
    "update.sh": 0o755,
    "rollback.sh": 0o755,
    "backup.sh": 0o755,
    "restore.sh": 0o755,
    "bootstrap-admin.sh": 0o755,
    "init-secrets.sh": 0o755,
    "lib.sh": 0o644,
}


class NoAliasDumper(yaml.SafeDumper):
    def ignore_aliases(self, data: object) -> bool:
        return True


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"YAML inválido: {path.relative_to(ROOT)}")
    return value


def merge(base: Any, overlay: Any, *, key: str = "") -> Any:
    """Merge suficiente para os overlays canônicos, preservando listas Compose."""
    if isinstance(base, dict) and isinstance(overlay, dict):
        result = copy.deepcopy(base)
        for child_key, value in overlay.items():
            result[child_key] = merge(result[child_key], value, key=child_key) if child_key in result else copy.deepcopy(value)
        return result
    if isinstance(base, list) and isinstance(overlay, list) and key in {
        "ports",
        "volumes",
        "secrets",
        "configs",
        "networks",
        "security_opt",
    }:
        result = copy.deepcopy(base)
        for value in overlay:
            if value not in result:
                result.append(copy.deepcopy(value))
        return result
    return copy.deepcopy(overlay)


def parse_env_example(path: Path) -> tuple[list[str], dict[str, str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    values: dict[str, str] = {}
    for line in lines:
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
            values[key] = value
    return lines, values


def env_expression(key: str, values: dict[str, str]) -> str:
    default = values.get(key, "")
    return f"${{{key}:-{default}}}"


def application_service(name: str) -> bool:
    return name in FIRST_PARTY_IMAGES or name.startswith("pige360-worker-")


def rewrite_mount(value: Any) -> Any:
    if not isinstance(value, str) or ":" not in value:
        return value
    source, remainder = value.split(":", 1)
    if source in VOLUME_PATHS:
        source = f"./volumes/{VOLUME_PATHS[source]}"
    elif source in CONFIG_MOUNTS:
        source = CONFIG_MOUNTS[source]
    elif source.startswith("${ANDROID_SDK_HOME:-"):
        source = "./volumes/toolchains/android-sdk"
    return f"{source}:{remainder}"


def gateway_service(environment: dict[str, str]) -> dict[str, Any]:
    return {
        "image": "${GATEWAY_IMAGE:-nginx:1.27.5-alpine}",
        "pull_policy": "missing",
        "depends_on": {
            "pige360-api": {"condition": "service_healthy"},
            "pige360-web": {"condition": "service_healthy"},
            "pige360-platform-console": {"condition": "service_healthy"},
            "pige360-branding-studio": {"condition": "service_healthy"},
            "pige360-tenant-download-center": {"condition": "service_healthy"},
        },
        "environment": {
            "PIGE360_BASE_DOMAIN": env_expression("PIGE360_BASE_DOMAIN", environment),
            "PLATFORM_API_HOST": env_expression("PLATFORM_API_HOST", environment),
            "PLATFORM_BRANDING_HOST": env_expression("PLATFORM_BRANDING_HOST", environment),
            "PLATFORM_CONSOLE_HOST": env_expression("PLATFORM_CONSOLE_HOST", environment),
            "PLATFORM_DOWNLOADS_HOST": env_expression("PLATFORM_DOWNLOADS_HOST", environment),
            "PLATFORM_OPS_HOST": env_expression("PLATFORM_OPS_HOST", environment),
        },
        "ports": ["${GATEWAY_BIND_HOST:-127.0.0.1}:${GATEWAY_PORT:-58080}:8080"],
        "volumes": ["./config/gateway/default.conf.template:/etc/nginx/templates/default.conf.template:ro"],
        "healthcheck": {
            "test": ["CMD-SHELL", "wget -q --spider http://127.0.0.1:8080/healthz"],
            "interval": "15s",
            "timeout": "5s",
            "retries": 20,
            "start_period": "10s",
        },
        "networks": ["pige360-app", "pige360-observability"],
        "restart": "unless-stopped",
        "read_only": True,
        "tmpfs": [
            "/etc/nginx/conf.d:mode=0755",
            "/var/cache/nginx:mode=0755",
            "/var/run:mode=0755",
            "/tmp:mode=1777",
        ],
        "security_opt": ["no-new-privileges:true"],
        "logging": {"driver": "json-file", "options": {"max-size": "20m", "max-file": "5"}},
    }


def volume_init_service() -> dict[str, Any]:
    return {
        "image": "busybox:1.37.0",
        "pull_policy": "missing",
        "user": "0:0",
        "network_mode": "none",
        "command": [
            "/bin/sh",
            "-ec",
            "mkdir -p /volumes/tenant-storage /volumes/loki && "
            "chown -R 10001:10001 /volumes/tenant-storage /volumes/loki && "
            "chmod 0770 /volumes/tenant-storage /volumes/loki",
        ],
        "volumes": [
            "./volumes/tenant-storage:/volumes/tenant-storage",
            "./volumes/loki:/volumes/loki",
        ],
        "restart": "no",
        "read_only": True,
        "tmpfs": ["/tmp:mode=1777"],
        "security_opt": ["no-new-privileges:true"],
        "logging": {"driver": "json-file", "options": {"max-size": "20m", "max-file": "5"}},
    }


def render_compose(config: dict[str, str], env_values: dict[str, str]) -> bytes:
    document = merge(load_yaml(ROOT / "compose.yaml"), load_yaml(ROOT / "compose.production.yaml"))
    document = merge(document, load_yaml(ROOT / "deploy/compose/compose.logging.yaml"))
    document["name"] = f"${{COMPOSE_PROJECT_NAME:-{config['project']}}}"
    for key in list(document):
        if isinstance(key, str) and key.startswith("x-"):
            document.pop(key)

    services = document.get("services")
    if not isinstance(services, dict):
        raise RuntimeError("Compose canônico sem services")

    for name, service in services.items():
        if not isinstance(service, dict):
            raise RuntimeError(f"Serviço inválido: {name}")
        service.pop("build", None)
        service.pop("ports", None)
        service["logging"] = {"driver": "json-file", "options": {"max-size": "20m", "max-file": "5"}}
        if name in FIRST_PARTY_IMAGES:
            image = FIRST_PARTY_IMAGES[name]
            service["image"] = f"${{PIGE360_IMAGE_REGISTRY:-ghcr.io/wkarts}}/{image}:${{PIGE360_IMAGE_TAG:-{config['tag']}}}"
            service["pull_policy"] = "always"
        elif name.startswith("pige360-worker-"):
            service["image"] = f"${{PIGE360_IMAGE_REGISTRY:-ghcr.io/wkarts}}/pige360-worker:${{PIGE360_IMAGE_TAG:-{config['tag']}}}"
            service["pull_policy"] = "always"

        if application_service(name):
            service["env_file"] = ["./.env"]

        raw_environment = service.get("environment")
        if application_service(name) and isinstance(raw_environment, dict):
            raw_environment["APP_ENV"] = env_expression("APP_ENV", env_values)
            raw_environment["APP_VERSION"] = env_expression("APP_VERSION", env_values)
            for env_key in APP_CONFIG_KEYS:
                raw_environment.setdefault(env_key, env_expression(env_key, env_values))

        volumes = service.get("volumes")
        if isinstance(volumes, list):
            service["volumes"] = [rewrite_mount(item) for item in volumes]

        if name in {
            "pige360-web",
            "pige360-platform-console",
            "pige360-branding-studio",
            "pige360-tenant-download-center",
        }:
            service["healthcheck"] = {
                "test": ["CMD-SHELL", "wget -q --spider http://127.0.0.1:8080/healthz"],
                "interval": "15s",
                "timeout": "5s",
                "retries": 12,
                "start_period": "10s",
            }

        if name.startswith("pige360-worker-"):
            command = service.get("command")
            if isinstance(command, list) and not any(str(item).startswith("--concurrency") for item in command):
                command.append("--concurrency=${PIGE360_WORKER_CONCURRENCY:-1}")
                command.extend(["--without-gossip", "--without-mingle"])

        if name == "pige360-otel-collector":
            service["profiles"] = ["otel"]

    ordered_services: dict[str, Any] = {}
    for name, service in services.items():
        if name == "pige360-app-init":
            ordered_services["pige360-volume-init"] = volume_init_service()
        ordered_services[name] = service
    document["services"] = services = ordered_services

    for name, service in services.items():
        if not isinstance(service, dict):
            continue
        if name == "pige360-volume-init":
            continue
        mounts = service.get("volumes") or []
        needs_volume_init = name in {"pige360-app-init", "pige360-api", "pige360-loki"} or any(
            isinstance(mount, str)
            and mount.startswith(("./volumes/tenant-storage:", "./volumes/loki:"))
            for mount in mounts
        )
        if not needs_volume_init:
            continue
        dependencies = service.setdefault("depends_on", {})
        if isinstance(dependencies, dict):
            dependencies["pige360-volume-init"] = {"condition": "service_completed_successfully"}

    services["pige360-gateway"] = gateway_service(env_values)

    networks = document.get("networks")
    if isinstance(networks, dict):
        for network in networks.values():
            if isinstance(network, dict):
                network.pop("name", None)

    document.pop("volumes", None)
    secrets = document.get("secrets")
    if isinstance(secrets, dict):
        for name in secrets:
            secrets[name] = {"file": f"./secrets/{name}.txt"}

    rendered = yaml.dump(
        document,
        Dumper=NoAliasDumper,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
        width=120,
    )
    header = (
        "# Gerado por scripts/deploy/generate_standalone_deployments.py.\n"
        "# Não edite diretamente; execute o gerador e versione o resultado.\n"
        f"# Ambiente: {config['description']}.\n\n"
    )
    return (header + rendered).encode("utf-8")


def replace_env_line(lines: list[str], key: str, value: str) -> None:
    prefix = f"{key}="
    for index, line in enumerate(lines):
        if line.startswith(prefix):
            lines[index] = f"{key}={value}"
            return
    lines.append(f"{key}={value}")


def render_env(config: dict[str, str]) -> bytes:
    lines, _ = parse_env_example(ROOT / ".env.example")
    base = config["base_domain"]
    changes = {
        "COMPOSE_PROJECT_NAME": config["project"],
        "PIGE360_PROJECT_NAME": config["project"],
        "PIGE360_ENVIRONMENT": "develop" if config["tag"] == "develop" else "production",
        "PIGE360_IMAGE_REGISTRY": "ghcr.io/wkarts",
        "PIGE360_IMAGE_TAG": config["tag"],
        "PIGE360_PULL_POLICY": "always",
        "PIGE360_SECRETS_DIR": "./secrets",
        "PIGE360_DATA_ROOT": "./volumes",
        "APP_ENV": config["app_env"],
        "APP_VERSION": config["version"],
        "APP_DEBUG": "true" if config["tag"] == "develop" else "false",
        "APP_DEMO_MODE": "false",
        "PIGE360_BASE_DOMAIN": base,
        "PLATFORM_CONTROL_BASE_DOMAIN": base,
        "PLATFORM_CONSOLE_HOST": f"console.{base}",
        "PLATFORM_API_HOST": f"api.{base}",
        "PLATFORM_BRANDING_HOST": f"branding.{base}",
        "PLATFORM_DOWNLOADS_HOST": f"downloads.{base}",
        "PLATFORM_OPS_HOST": f"ops.{base}",
        "TENANT_DEFAULT_BASE_DOMAIN": base,
        "TENANT_WILDCARD_HOST": f"*.{base}",
        "TENANT_CANONICAL_HOST_TEMPLATE": f"{{tenant}}.{base}",
        "TENANT_CUSTOM_DOMAIN_CNAME_TARGET": f"edge.{base}",
        "ALLOWED_PLATFORM_HOSTS": f"console.{base},api.{base}",
        "CORS_ALLOWED_ORIGINS": f"https://console.{base},http://127.0.0.1:{config['gateway_port']}",
        "GATEWAY_IMAGE": "nginx:1.27.5-alpine",
        "GATEWAY_BIND_HOST": "127.0.0.1",
        "GATEWAY_PORT": config["gateway_port"],
        "WEB_BIND_HOST": "127.0.0.1",
        "WEB_BIND_PORT": config["gateway_port"],
        "WEB_PUBLISHED_PORT": config["gateway_port"],
        "CONSOLE_BIND_HOST": "127.0.0.1",
        "CONSOLE_BIND_PORT": str(int(config["gateway_port"]) + 1),
        "CONTROL_WEB_BIND_HOST": "127.0.0.1",
        "CONTROL_WEB_PUBLISHED_PORT": str(int(config["gateway_port"]) + 1),
        "BRANDING_BIND_HOST": "127.0.0.1",
        "BRANDING_BIND_PORT": str(int(config["gateway_port"]) + 2),
        "BRANDING_PUBLISHED_PORT": str(int(config["gateway_port"]) + 2),
        "DOWNLOADS_BIND_HOST": "127.0.0.1",
        "DOWNLOADS_BIND_PORT": str(int(config["gateway_port"]) + 3),
        "DOWNLOADS_PUBLISHED_PORT": str(int(config["gateway_port"]) + 3),
        "PIGE360_WORKER_CONCURRENCY": "1" if config["tag"] == "develop" else "2",
        "READINESS_REQUIRE_REDIS": "true",
        "READINESS_REQUIRE_RABBITMQ": "true",
        "READINESS_REQUIRE_OBJECT_STORAGE": "true",
        "READINESS_TIMEOUT_SECONDS": "5",
        "DATABASE_POOL_SIZE": "10",
        "DATABASE_MAX_OVERFLOW": "10",
        "APP_LOGIN_MAX_ATTEMPTS": "5",
        "APP_LOGIN_LOCKOUT_MINUTES": "15",
        "MINIO_REGION": "us-east-1",
        "NOTIFICATION_SCHEDULER_INTERVAL_SECONDS": "60",
        "OUTBOX_PUBLISH_INTERVAL_SECONDS": "5",
        "OTEL_ENABLED": "false",
        "TRUSTED_PROXY_CIDRS": "127.0.0.1/32,172.16.0.0/12",
    }
    for key, value in changes.items():
        replace_env_line(lines, key, value)

    banner = [
        "# ============================================================================",
        f"# PIGE360 {config['version']} — {config['description']}",
        "# Copie para .env. Segredos reais ficam exclusivamente em ./secrets/*.txt.",
        "# ============================================================================",
        "",
    ]
    return ("\n".join(banner + lines).rstrip() + "\n").encode("utf-8")


def shell_lib(default_project: str) -> bytes:
    return f'''#!/bin/sh

set -eu

deployment_root() {{ CDPATH= cd -- "$(dirname -- "$0")" && pwd; }}
die() {{ printf '%s\\n' "ERRO: $*" >&2; exit 1; }}
info() {{ printf '%s\\n' "PIGE360: $*"; }}
require() {{ command -v "$1" >/dev/null 2>&1 || die "comando obrigatório ausente: $1"; }}

load_context() {{
  ROOT="$(deployment_root)"
  ENV_FILE="${{PIGE360_ENV_FILE:-$ROOT/.env}}"
  COMPOSE_FILE="${{PIGE360_COMPOSE_FILE:-$ROOT/compose.yaml}}"
  [ -f "$ENV_FILE" ] || die "arquivo ausente: $ENV_FILE (copie .env.example para .env)"
  export ROOT ENV_FILE COMPOSE_FILE
}}

compose() {{
  docker compose --project-directory "$ROOT" --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
}}

env_value() {{
  awk -F= -v wanted="$1" '$0 !~ /^[[:space:]]*#/ && $1 == wanted {{sub(/^[^=]*=/, ""); sub(/\\r$/, ""); print; exit}}' "$ENV_FILE"
}}

set_env_value() {{
  key="$1" value="$2" file="$ENV_FILE" temporary="$ENV_FILE.tmp.$$"
  awk -F= -v key="$key" -v value="$value" '
    BEGIN {{ found=0 }}
    $1 == key {{ print key "=" value; found=1; next }}
    {{ print }}
    END {{ if (!found) print key "=" value }}
  ' "$file" > "$temporary"
  chmod 600 "$temporary"
  mv "$temporary" "$file"
}}

validate_tag() {{
  printf '%s\\n' "$1" | grep -Eq '^(develop|develop-[0-9a-f]{{12}}|[0-9]+\\.[0-9]+\\.[0-9]+([+-][0-9A-Za-z.-]+)?)$' \
    || die "tag inválida: $1 (use develop, develop-<sha12> ou SemVer)"
}}

validate_environment_tag() {{
  tag="$1"
  validate_tag "$tag"
  if [ "$(env_value PIGE360_ENVIRONMENT)" = production ]; then
    printf '%s\\n' "$tag" | grep -Eq '^[0-9]+\\.[0-9]+\\.[0-9]+(\\+[0-9A-Za-z.-]+)?$' \
      || die "produção exige tag SemVer estável e imutável, recebido: $tag"
  fi
}}

path_mode() {{
  if stat -c '%a' "$1" >/dev/null 2>&1; then stat -c '%a' "$1"
  elif stat -f '%Lp' "$1" >/dev/null 2>&1; then stat -f '%Lp' "$1"
  else die "não foi possível verificar permissões de $1"
  fi
}}

acquire_operation_lock() {{
  prepare_directories
  OPERATION_LOCK="$ROOT/.state/operation.lock"
  if ! mkdir "$OPERATION_LOCK" 2>/dev/null; then
    owner="$(cat "$OPERATION_LOCK/pid" 2>/dev/null || printf '?')"
    die "outra operação está ativa (pid=$owner)"
  fi
  printf '%s\\n' "$$" > "$OPERATION_LOCK/pid"
  export OPERATION_LOCK
}}

release_operation_lock() {{
  [ -n "${{OPERATION_LOCK:-}}" ] || return 0
  rm -f "$OPERATION_LOCK/pid"
  rmdir "$OPERATION_LOCK" 2>/dev/null || true
  OPERATION_LOCK=''
}}

prepare_directories() {{
  mkdir -p "$ROOT/volumes" "$ROOT/secrets" "$ROOT/.state"
  for directory in postgres-control postgres-tenants redis rabbitmq minio clamav tenant-storage prometheus grafana loki build-source toolchains/android-sdk; do
    mkdir -p "$ROOT/volumes/$directory"
  done
  chmod 700 "$ROOT/secrets" "$ROOT/.state"
}}

require_docker() {{
  require docker
  docker compose version >/dev/null 2>&1 || die "Docker Compose v2 é obrigatório"
}}

default_project() {{ printf '%s\\n' '{default_project}'; }}
'''.encode("utf-8")


def init_secrets_script() -> bytes:
    # Reutiliza o bootstrap endurecido do fonte para que o standalone preserve
    # criação atômica, idempotência e recusa explícita de links simbólicos.
    source = (ROOT / "scripts/local/init-secrets.sh").read_text(encoding="utf-8")
    needle = 'root="${1:-runtime-secrets}"'
    if needle not in source:
        raise RuntimeError("bootstrap canônico de segredos não contém o diretório padrão esperado")
    source = source.replace(
        needle,
        'script_root="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"\n'
        'root="${1:-${PIGE360_SECRETS_DIR:-$script_root/secrets}}"',
        1,
    )
    return source.encode("utf-8")


def operational_scripts(config: dict[str, str]) -> dict[str, bytes]:
    install = '''#!/bin/sh
set -eu
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
. "$ROOT/lib.sh"
[ -f "$ROOT/.env" ] || { cp "$ROOT/.env.example" "$ROOT/.env"; chmod 600 "$ROOT/.env"; }
load_context
prepare_directories
"$ROOT/init-secrets.sh"
require_docker
"$ROOT/validate.sh"
if [ "${GHCR_USERNAME:-}" ] && [ "${GHCR_TOKEN:-}" ]; then
  printf '%s' "$GHCR_TOKEN" | docker login ghcr.io -u "$GHCR_USERNAME" --password-stdin
fi
info "baixando imagens $(env_value PIGE360_IMAGE_REGISTRY):$(env_value PIGE360_IMAGE_TAG)"
compose pull
if ! compose up -d --remove-orphans --wait --wait-timeout "${PIGE360_STARTUP_TIMEOUT_SECONDS:-600}"; then
  compose ps --all >&2 || true
  compose logs --no-color --tail=200 pige360-app-init pige360-api pige360-gateway >&2 || true
  die "stack não iniciou"
fi
"$ROOT/healthcheck.sh"
info "instalação concluída em http://$(env_value GATEWAY_BIND_HOST):$(env_value GATEWAY_PORT)"
'''.encode("utf-8")
    validate = '''#!/bin/sh
set -eu
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
. "$ROOT/lib.sh"
load_context
require_docker
python3 "${PIGE360_SOURCE_ROOT:-$ROOT/../..}/scripts/deploy/generate_standalone_deployments.py" --check 2>/dev/null || {
  [ ! -f "${PIGE360_SOURCE_ROOT:-$ROOT/../..}/scripts/deploy/generate_standalone_deployments.py" ] || die "deployment divergiu do gerador"
}
for script in install validate healthcheck logs stop update rollback bootstrap-admin init-secrets backup restore; do
  path="$ROOT/$script.sh"
  [ -x "$path" ] || die "script operacional ausente ou sem execução: $script.sh"
  sh -n "$path" || die "sintaxe shell inválida: $script.sh"
done
[ -f "$ROOT/tools/backup_manifest.py" ] || die "validador de backup ausente"
tag="$(env_value PIGE360_IMAGE_TAG)"
registry="$(env_value PIGE360_IMAGE_REGISTRY)"
[ -n "$tag" ] || die "PIGE360_IMAGE_TAG vazio"
[ "$registry" = "ghcr.io/wkarts" ] || die "PIGE360_IMAGE_REGISTRY deve ser ghcr.io/wkarts"
validate_environment_tag "$tag"
[ "$(path_mode "$ROOT/secrets")" = 700 ] || die "o diretório secrets deve usar modo 0700"
for required in app_jwt_secret bootstrap_token minio_access_key minio_secret_key postgres_control_password postgres_tenant_password grafana_admin_password database_secret_key redis_password rabbitmq_password worker_context_signing_key build_farm_token; do
  [ -s "$ROOT/secrets/$required.txt" ] || die "segredo ausente: secrets/$required.txt"
  [ "$(path_mode "$ROOT/secrets/$required.txt")" = 444 ] || die "secrets/$required.txt deve usar modo 0444"
done
for optional in cloudflare_control_tunnel_token cloudflare_tenant_tunnel_token cloudflare_api_token connect_api_key; do
  [ -e "$ROOT/secrets/$optional.txt" ] || die "arquivo opcional ausente: secrets/$optional.txt"
  [ "$(path_mode "$ROOT/secrets/$optional.txt")" = 444 ] || die "secrets/$optional.txt deve usar modo 0444"
done
compose config --quiet
rendered="$(mktemp)"
trap 'rm -f "$rendered"' EXIT
compose config > "$rendered"
if grep -Eq '^[[:space:]]+build:' "$rendered"; then die "Compose standalone contém build"; fi
if grep -Eq 'source: (pige360-|/var/lib/docker/volumes)' "$rendered"; then die "Compose standalone contém volume global"; fi
publishers="$(awk '/^[[:space:]]{4}ports:/{print previous} {if ($0 ~ /^  [a-zA-Z0-9_-]+:$/) {previous=$1; sub(":$", "", previous)}}' "$rendered")"
[ "$publishers" = "pige360-gateway" ] || die "somente pige360-gateway pode publicar porta (encontrado: $publishers)"
info "Compose standalone validado: projeto=$(env_value COMPOSE_PROJECT_NAME), tag=$tag"
'''.encode("utf-8")
    health = '''#!/bin/sh
set -eu
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
. "$ROOT/lib.sh"
load_context
require_docker
require curl
port="$(env_value GATEWAY_PORT)"
api_host="$(env_value PLATFORM_API_HOST)"
console_host="$(env_value PLATFORM_CONSOLE_HOST)"
branding_host="$(env_value PLATFORM_BRANDING_HOST)"
downloads_host="$(env_value PLATFORM_DOWNLOADS_HOST)"
tenant_host="healthcheck.$(env_value PIGE360_BASE_DOMAIN)"
attempt=1
while [ "$attempt" -le "${PIGE360_HEALTH_ATTEMPTS:-60}" ]; do
  if curl -fsS -H "Host: $api_host" "http://127.0.0.1:$port/api/v1/health/ready" >/dev/null 2>&1 \
    && curl -fsS -H "Host: $tenant_host" "http://127.0.0.1:$port/healthz" >/dev/null 2>&1 \
    && curl -fsS -H "Host: $console_host" "http://127.0.0.1:$port/healthz" >/dev/null 2>&1 \
    && curl -fsS -H "Host: $branding_host" "http://127.0.0.1:$port/healthz" >/dev/null 2>&1 \
    && curl -fsS -H "Host: $downloads_host" "http://127.0.0.1:$port/healthz" >/dev/null 2>&1; then
    running="$(compose ps --status running --services)"
    required_running=true
    for service in pige360-api pige360-web pige360-platform-console pige360-branding-studio pige360-tenant-download-center pige360-worker-default pige360-beat pige360-gateway; do
      printf '%s\\n' "$running" | grep -Fx "$service" >/dev/null 2>&1 || required_running=false
    done
    if [ "$required_running" = true ] \
      && compose exec -T pige360-worker-default celery -A app.worker inspect ping --timeout 10 >/dev/null 2>&1 \
      && compose exec -T pige360-beat sh -ec 'kill -0 1' >/dev/null 2>&1; then
      compose ps
      info "readiness API, quatro frontends, worker e beat aprovado"
      exit 0
    fi
  fi
  sleep "${PIGE360_HEALTH_DELAY_SECONDS:-5}"
  attempt=$((attempt + 1))
done
compose ps --all >&2 || true
compose logs --no-color --tail=200 pige360-app-init pige360-api pige360-gateway >&2 || true
die "readiness não aprovado"
'''.encode("utf-8")
    logs = '''#!/bin/sh
set -eu
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"; . "$ROOT/lib.sh"; load_context; require_docker
compose logs --no-color --tail "${PIGE360_LOG_TAIL:-250}" "$@"
'''.encode("utf-8")
    stop = '''#!/bin/sh
set -eu
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"; . "$ROOT/lib.sh"; load_context; require_docker
case "${1:-stop}" in
  stop) compose stop ;;
  down) compose down --remove-orphans ;;
  *) die "uso: $0 [stop|down]; volumes nunca são removidos por este script" ;;
esac
'''.encode("utf-8")
    update = '''#!/bin/sh
set -eu
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"; . "$ROOT/lib.sh"; load_context; prepare_directories; require_docker
new_tag="${1:-$(env_value PIGE360_IMAGE_TAG)}"; validate_environment_tag "$new_tag"
old_tag="$(env_value PIGE360_IMAGE_TAG)"; stamp="$(date -u +%Y%m%dT%H%M%SZ)"
cp "$ENV_FILE" "$ROOT/.state/env-$stamp"; chmod 600 "$ROOT/.state/env-$stamp"
printf '%s\\n' "$old_tag" > "$ROOT/.state/previous-image-tag"
set_env_value PIGE360_IMAGE_TAG "$new_tag"
if compose config --quiet && compose pull && compose up -d --remove-orphans --wait --wait-timeout "${PIGE360_STARTUP_TIMEOUT_SECONDS:-600}" && "$ROOT/healthcheck.sh"; then
  info "atualização concluída: $old_tag -> $new_tag"
  exit 0
fi
info "atualização falhou; restaurando tag $old_tag"
set_env_value PIGE360_IMAGE_TAG "$old_tag"
compose up -d --remove-orphans || true
exit 1
'''.encode("utf-8")
    rollback = '''#!/bin/sh
set -eu
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"; . "$ROOT/lib.sh"; load_context
tag="${1:-}"
[ -n "$tag" ] || tag="$(cat "$ROOT/.state/previous-image-tag" 2>/dev/null || true)"
[ -n "$tag" ] || die "uso: $0 TAG_IMUTAVEL; nenhuma tag anterior registrada"
case "$tag" in develop) die "rollback exige develop-<sha12> ou SemVer imutável, não a tag móvel develop";; esac
validate_environment_tag "$tag"
exec "$ROOT/update.sh" "$tag"
'''.encode("utf-8")
    bootstrap_admin = '''#!/bin/sh
set -eu
password="${PIGE360_BOOTSTRAP_PASSWORD:-}"
unset PIGE360_BOOTSTRAP_PASSWORD 2>/dev/null || true
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"; . "$ROOT/lib.sh"; load_context
require python3
email="${1:-}"
case "$email" in *@*.*) ;; *) die "uso: $0 EMAIL" ;; esac
restore_tty=false
if [ -z "$password" ]; then
  [ -t 0 ] || die "execute em terminal ou forneça PIGE360_BOOTSTRAP_PASSWORD somente para este processo"
  printf '%s' 'Senha inicial do administrador: ' >&2
  trap 'if [ "$restore_tty" = true ]; then stty echo; printf "\\n" >&2; fi' EXIT INT TERM HUP
  stty -echo
  restore_tty=true
  IFS= read -r password
  stty echo
  restore_tty=false
  printf '\n' >&2
fi
[ "${#password}" -ge 12 ] || die "a senha precisa ter ao menos 12 caracteres"
port="$(env_value GATEWAY_PORT)"
host="$(env_value PLATFORM_CONSOLE_HOST)"
token_file="$ROOT/secrets/bootstrap_token.txt"
[ -s "$token_file" ] || die "segredo de bootstrap ausente"
response="$(printf '%s\\n%s\\n' "$email" "$password" | python3 -c '
import json, sys, urllib.error, urllib.request
email = sys.stdin.readline().rstrip("\\n")
password = sys.stdin.readline().rstrip("\\n")
url, host, token_file = sys.argv[1:]
token = open(token_file, encoding="utf-8").read().strip()
request = urllib.request.Request(
    url,
    data=json.dumps({"email": email, "password": password}).encode(),
    headers={"Content-Type": "application/json", "Host": host, "X-Bootstrap-Token": token},
    method="POST",
)
try:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=30) as result:
        print(result.read().decode())
except urllib.error.HTTPError as error:
    sys.stderr.write(error.read().decode() + "\\n")
    raise SystemExit(1)
' "http://127.0.0.1:$port/api/v1/platform/bootstrap" "$host" "$token_file")"
password=''
printf '%s\\n' "$response"
info "bootstrap administrativo concluído ou confirmado como idempotente para $email"
'''.encode("utf-8")
    backup = '''#!/bin/sh
set -eu
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"; . "$ROOT/lib.sh"; load_context
require_docker
require python3
"$ROOT/validate.sh"
"$ROOT/healthcheck.sh"
acquire_operation_lock
trap release_operation_lock EXIT

out="${1:-$ROOT/backups/$(date -u +%Y%m%dT%H%M%SZ)}"
case "$out" in /*) ;; *) out="$ROOT/$out" ;; esac
[ "$out" != / ] && [ "$out" != "$ROOT" ] || die "destino de backup inseguro: $out"
[ ! -e "$out" ] || die "destino de backup já existe: $out"
mkdir -p "$(dirname -- "$out")"
stage="$out.partial.$$"
[ ! -e "$stage" ] || die "área parcial já existe: $stage"
mkdir -m 700 -p "$stage/tenant-databases" "$stage/objects" \
  "$stage/configuration/environment" "$stage/configuration/secrets"
umask 077

writer_services=''
for service in $(compose ps --status running --services); do
  case "$service" in
    pige360-api|pige360-app-factory-api|pige360-beat|pige360-worker-*|pige360-builder-*)
      writer_services="$writer_services $service"
      ;;
  esac
done
[ -n "$writer_services" ] || die "nenhum processo de escrita ativo; o stack não está no estado esperado"
quiesced=false
cleanup_backup() {
  status=$?
  trap - EXIT HUP INT TERM
  set +e
  if [ "$quiesced" = true ]; then
    compose up -d $writer_services >/dev/null 2>&1 || status=1
  fi
  release_operation_lock
  if [ "$status" -ne 0 ]; then
    printf '%s\\n' "ERRO: backup não concluído; parcial preservado em $stage" >&2
  fi
  exit "$status"
}
trap cleanup_backup EXIT
trap 'exit 130' HUP INT TERM

info "suspendendo processos de escrita para snapshot consistente da aplicação"
# A lista contém somente nomes obtidos de `docker compose config --services`.
# A expansão é intencional para passá-los como argumentos separados.
compose stop $writer_services
quiesced=true

tab="$(printf '\\t')"
catalog_sql="SELECT id,code,status,database_name,database_user,bucket_name FROM platform_tenants WHERE status IN ('active','degraded','suspended') ORDER BY id"
compose exec -T pige360-postgres-control \
  psql -X -U pige360_control -d platform_control -v ON_ERROR_STOP=1 -A -t -F "$tab" -c "$catalog_sql" \
  > "$stage/tenants.tsv"
python3 "$ROOT/tools/backup_manifest.py" validate-catalog "$stage" >/dev/null

info "exportando roles e banco do Control Plane"
compose exec -T pige360-postgres-control pg_dumpall -U pige360_control --globals-only \
  > "$stage/postgres-control-globals.sql"
compose exec -T pige360-postgres-control \
  pg_dump -U pige360_control --format=custom --no-owner --no-privileges platform_control \
  > "$stage/platform-control.dump"
compose exec -T pige360-postgres-control pg_restore --list \
  < "$stage/platform-control.dump" >/dev/null

info "exportando roles e bancos dedicados dos tenants"
compose exec -T pige360-postgres-tenants pg_dumpall -U pige360_tenant_admin --globals-only \
  > "$stage/postgres-tenant-globals.sql"
while IFS="$tab" read -r tenant_id code status database_name database_user bucket_name; do
  [ -n "$tenant_id" ] || continue
  compose exec -T pige360-postgres-tenants \
    pg_dump -U pige360_tenant_admin --format=custom --no-owner --no-privileges "$database_name" \
    > "$stage/tenant-databases/${database_name}.dump"
  compose exec -T pige360-postgres-tenants pg_restore --list \
    < "$stage/tenant-databases/${database_name}.dump" >/dev/null
done < "$stage/tenants.tsv"
{
  printf 'control='
  compose exec -T pige360-postgres-control pg_dump --version
  printf 'tenants='
  compose exec -T pige360-postgres-tenants pg_dump --version
} > "$stage/postgres-versions.txt"

info "arquivando o armazenamento local dos tenants"
compose run --rm --no-deps --user 0:0 -v "$stage:/backup" \
  --entrypoint python pige360-app-init -c '
from pathlib import Path
import tarfile

source = Path("/var/lib/pige360/tenants")
for item in source.rglob("*"):
    if item.is_symlink():
        raise SystemExit(f"link simbólico recusado: {item.relative_to(source)}")
with tarfile.open("/backup/tenant-storage.tar.gz", "w:gz") as archive:
    for item in sorted(source.iterdir()) if source.exists() else ():
        archive.add(item, arcname=item.name, recursive=True)
'

{
  printf '%s\\n' pige360-platform
  cut -f6 "$stage/tenants.tsv"
} | sed '/^$/d' | LC_ALL=C sort -u > "$stage/buckets.txt"

info "espelhando os buckets MinIO"
compose run --rm --no-deps --user 0:0 -v "$stage:/backup" \
  --entrypoint /bin/sh pige360-minio-init -ec '
  access="$(cat "$MINIO_ACCESS_KEY_FILE")"
  secret="$(cat "$MINIO_SECRET_KEY_FILE")"
  mc alias set snapshot "$MINIO_ENDPOINT" "$access" "$secret" >/dev/null
  while IFS= read -r bucket; do
    [ -n "$bucket" ] || continue
    mkdir -p "/backup/objects/$bucket"
    mc stat "snapshot/$bucket" >/dev/null
    mc mirror --preserve "snapshot/$bucket" "/backup/objects/$bucket"
  done < /backup/buckets.txt
'

catalog_after="$stage/tenants-after.tsv"
compose exec -T pige360-postgres-control \
  psql -X -U pige360_control -d platform_control -v ON_ERROR_STOP=1 -A -t -F "$tab" -c "$catalog_sql" \
  > "$catalog_after"
cmp -s "$stage/tenants.tsv" "$catalog_after" || die "catálogo de tenants mudou durante o backup"
rm -f "$catalog_after"

info "copiando configuração de recuperação em área separada"
[ ! -L "$ENV_FILE" ] || die "env-file simbólico recusado"
cp "$ENV_FILE" "$stage/configuration/environment/.env"
chmod 400 "$stage/configuration/environment/.env"
for source in "$ROOT"/secrets/*.txt; do
  [ -f "$source" ] && [ ! -L "$source" ] || die "secret ausente ou simbólico: $source"
  target="$stage/configuration/secrets/${source##*/}"
  cp "$source" "$target"
  chmod 400 "$target"
done

case "$(basename -- "$(dirname -- "$ROOT")")" in
  dockge|cloudpanel|portainer) backup_target="$(basename -- "$(dirname -- "$ROOT")")" ;;
  *) backup_target=base ;;
esac
database_key_fingerprint="$(python3 -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())' "$ROOT/secrets/database_secret_key.txt")"
python3 "$ROOT/tools/backup_manifest.py" create "$stage" \
  --version "$(env_value APP_VERSION)" --target "$backup_target" --image-mode registry \
  --database-key-fingerprint "$database_key_fingerprint" >/dev/null
python3 "$ROOT/tools/backup_manifest.py" verify "$stage" >/dev/null
mv "$stage" "$out"

info "reativando processos de escrita"
compose up -d $writer_services
quiesced=false
"$ROOT/healthcheck.sh"
release_operation_lock
trap - EXIT HUP INT TERM
info "backup verificável concluído em $out"
info "ATENÇÃO: configuration/secrets contém segredos em texto claro; o backup não é criptografado"
'''.encode("utf-8")
    restore = '''#!/bin/sh
set -eu
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"; . "$ROOT/lib.sh"; load_context
archive=''
confirmation=''
usage() { printf '%s\\n' "uso: $0 DIRETORIO_BACKUP --confirm RESTORE-PIGE360"; }
while [ "$#" -gt 0 ]; do
  case "$1" in
    --confirm) [ "$#" -ge 2 ] || { usage >&2; exit 2; }; confirmation="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    -*) usage >&2; exit 2 ;;
    *) [ -z "$archive" ] || { usage >&2; exit 2; }; archive="$1"; shift ;;
  esac
done
[ -n "$archive" ] || { usage >&2; exit 2; }
[ "$confirmation" = RESTORE-PIGE360 ] || die "restauração recusada: use --confirm RESTORE-PIGE360"
case "$archive" in /*) ;; *) archive="$(pwd -P)/$archive" ;; esac
[ -d "$archive" ] && [ ! -L "$archive" ] || die "diretório de backup ausente ou simbólico: $archive"
require python3
require_docker
python3 "$ROOT/tools/backup_manifest.py" verify "$archive" >/dev/null
"$ROOT/validate.sh"

expected_key_fingerprint="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["database_secret_key_sha256"])' "$archive/manifest.json")"
actual_key_fingerprint="$(python3 -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())' "$ROOT/secrets/database_secret_key.txt")"
[ "$actual_key_fingerprint" = "$expected_key_fingerprint" ] || \
  die "database_secret_key não corresponde ao backup; restaure manualmente configuration/secrets antes de continuar"

acquire_operation_lock
restore_complete=false
restored_catalog=''
cleanup_restore() {
  status=$?
  trap - EXIT HUP INT TERM
  [ -z "$restored_catalog" ] || rm -f "$restored_catalog"
  release_operation_lock
  if [ "$restore_complete" != true ]; then
    printf '%s\\n' "ERRO: restauração não concluída; stack permanece fail-closed para inspeção" >&2
    status=1
  fi
  exit "$status"
}
trap cleanup_restore EXIT
trap 'exit 130' HUP INT TERM

info "parando o stack antes da restauração destrutiva"
compose stop
compose up -d --wait --wait-timeout "${PIGE360_STARTUP_TIMEOUT_SECONDS:-600}" \
  pige360-postgres-control pige360-postgres-tenants pige360-minio

backup_postgres_major="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["postgres_major"])' "$archive/manifest.json")"
runtime_postgres_major="$(compose exec -T pige360-postgres-control pg_dump --version | sed -n 's/.*PostgreSQL) \\([0-9][0-9]*\\).*/\\1/p')"
[ -n "$runtime_postgres_major" ] && [ "$runtime_postgres_major" = "$backup_postgres_major" ] || \
  die "major PostgreSQL do backup ($backup_postgres_major) difere do runtime (${runtime_postgres_major:-desconhecido})"

info "restaurando banco do Control Plane"
compose exec -T pige360-postgres-control psql -X -U pige360_control -d postgres -v ON_ERROR_STOP=1 \
  -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='platform_control' AND pid <> pg_backend_pid()" >/dev/null
compose exec -T pige360-postgres-control dropdb -U pige360_control --if-exists platform_control
compose exec -T pige360-postgres-control createdb -U pige360_control -O pige360_control platform_control
compose exec -T pige360-postgres-control \
  pg_restore -U pige360_control --exit-on-error --no-owner --no-privileges -d platform_control \
  < "$archive/platform-control.dump"

compose run --rm --no-deps -w /opt/pige360 --entrypoint python pige360-app-init \
  -m alembic -c backend/alembic_control/alembic.ini upgrade head

tab="$(printf '\\t')"
restored_catalog="$(mktemp)"
catalog_sql="SELECT id,code,status,database_name,database_user,bucket_name FROM platform_tenants WHERE status IN ('active','degraded','suspended') ORDER BY id"
compose exec -T pige360-postgres-control \
  psql -X -U pige360_control -d platform_control -v ON_ERROR_STOP=1 -A -t -F "$tab" -c "$catalog_sql" \
  > "$restored_catalog"
cmp -s "$archive/tenants.tsv" "$restored_catalog" || die "catálogo restaurado diverge do backup"
rm -f "$restored_catalog"
restored_catalog=''

compose run --rm --no-deps --entrypoint python pige360-app-init \
  -m app.shared.database.migrate_tenants --ensure-resources --skip-migrations

info "restaurando bancos dedicados dos tenants"
while IFS="$tab" read -r tenant_id code status database_name database_user bucket_name; do
  [ -n "$tenant_id" ] || continue
  compose exec -T pige360-postgres-tenants psql -X -U pige360_tenant_admin -d postgres -v ON_ERROR_STOP=1 \
    -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='${database_name}' AND pid <> pg_backend_pid()" >/dev/null
  compose exec -T pige360-postgres-tenants dropdb -U pige360_tenant_admin --if-exists "$database_name"
  compose exec -T pige360-postgres-tenants createdb -U pige360_tenant_admin -O "$database_user" "$database_name"
  compose exec -T pige360-postgres-tenants \
    pg_restore -U pige360_tenant_admin --role "$database_user" --exit-on-error --no-owner --no-privileges \
    -d "$database_name" < "$archive/tenant-databases/${database_name}.dump"
done < "$archive/tenants.tsv"

info "restaurando buckets MinIO"
compose run --rm --no-deps --user 0:0 -v "$archive:/backup:ro" \
  --entrypoint /bin/sh pige360-minio-init -ec '
  access="$(cat "$MINIO_ACCESS_KEY_FILE")"
  secret="$(cat "$MINIO_SECRET_KEY_FILE")"
  mc alias set restore "$MINIO_ENDPOINT" "$access" "$secret" >/dev/null
  while IFS= read -r bucket; do
    [ -n "$bucket" ] || continue
    mc mb --ignore-existing "restore/$bucket" >/dev/null
    mc mirror --overwrite --remove "/backup/objects/$bucket" "restore/$bucket"
  done < /backup/buckets.txt
'

info "restaurando armazenamento local dos tenants"
compose run --rm --no-deps --user 0:0 -v "$archive:/backup:ro" \
  --entrypoint python pige360-app-init -c '
from pathlib import Path, PurePosixPath
import shutil
import tarfile

target = Path("/var/lib/pige360/tenants")
target.mkdir(parents=True, exist_ok=True)
with tarfile.open("/backup/tenant-storage.tar.gz", "r:gz") as source:
    for member in source.getmembers():
        path = PurePosixPath(member.name)
        if not member.name or path.is_absolute() or ".." in path.parts or member.issym() or member.islnk() or member.isdev():
            raise SystemExit(f"entrada insegura no tenant storage: {member.name!r}")
    for item in target.iterdir():
        if item.is_dir() and not item.is_symlink():
            shutil.rmtree(item)
        else:
            item.unlink()
    source.extractall(target, filter="data")
'
compose run --rm --no-deps pige360-volume-init

info "aplicando migrations idempotentes e reativando o stack"
compose run --rm --no-deps pige360-app-init
compose up -d --remove-orphans --wait --wait-timeout "${PIGE360_STARTUP_TIMEOUT_SECONDS:-600}"
"$ROOT/healthcheck.sh"
restore_complete=true
release_operation_lock
trap - EXIT HUP INT TERM
info "restauração concluída e validada; .env e secrets do backup não foram sobrescritos automaticamente"
'''.encode("utf-8")
    return {
        "lib.sh": shell_lib(config["project"]),
        "init-secrets.sh": init_secrets_script(),
        "install.sh": install,
        "validate.sh": validate,
        "healthcheck.sh": health,
        "logs.sh": logs,
        "stop.sh": stop,
        "update.sh": update,
        "rollback.sh": rollback,
        "bootstrap-admin.sh": bootstrap_admin,
        "backup.sh": backup,
        "restore.sh": restore,
    }


def gateway_template() -> bytes:
    return b'''map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}

map $http_x_forwarded_proto $pige360_forwarded_proto {
    default $http_x_forwarded_proto;
    ''      $scheme;
}

map $host $pige360_frontend {
    hostnames;
    default                         pige360-web:8080;
    ${PLATFORM_CONSOLE_HOST}        pige360-platform-console:8080;
    ${PLATFORM_BRANDING_HOST}       pige360-branding-studio:8080;
    ${PLATFORM_DOWNLOADS_HOST}      pige360-tenant-download-center:8080;
    ${PLATFORM_OPS_HOST}            pige360-grafana:3000;
}

server {
    listen 8080;
    server_tokens off;
    client_max_body_size 100m;

    location = /healthz {
        access_log off;
        add_header Content-Type text/plain;
        return 200 "ok\n";
    }

    # Metricas sao coletadas somente pela rede Docker interna.
    location = /api/v1/metrics {
        access_log off;
        return 404;
    }

    location /api/ {
        proxy_pass http://pige360-api:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $pige360_forwarded_proto;
        proxy_set_header X-Request-ID $request_id;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
    }

    location / {
        resolver 127.0.0.11 valid=30s ipv6=off;
        proxy_pass http://$pige360_frontend;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $pige360_forwarded_proto;
        proxy_set_header X-Request-ID $request_id;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
    }
}
'''


def readme(config: dict[str, str]) -> bytes:
    production = config["tag"] != "develop"
    immutable_note = (
        "A tag padrão é SemVer imutável. Para atualizar, informe outra SemVer publicada."
        if production
        else "Para rollback use preferencialmente `develop-<sha12>`; `develop` é um canal móvel."
    )
    return f'''# PIGE360 — {config['description'].capitalize()}

Este diretório é um deployment **standalone, image-only**. Ele não compila o
código-fonte no servidor e não depende dos Compose da raiz do repositório.

## Instalação

```bash
cp .env.example .env
# revise domínios e opções; segredos serão criados em ./secrets
./install.sh
./bootstrap-admin.sh admin@seu-dominio.com.br
```

Registro privado, se aplicável:

```bash
export GHCR_USERNAME=SEU_USUARIO
export GHCR_TOKEN=SEU_TOKEN_READ_PACKAGES
./install.sh
```

O único bind publicado é `127.0.0.1:{config['gateway_port']}` no serviço
`pige360-gateway`. PostgreSQL, Redis, RabbitMQ, MinIO e observabilidade permanecem
nas redes Docker. Configure CloudPanel/Nginx para encaminhar o domínio e wildcard
para esse gateway, preservando o cabeçalho `Host`.

## Dockge, CloudPanel e Portainer

- Dockge: importe `compose.dockge.yaml` e o `.env` deste diretório.
- CloudPanel: use `compose.cloudpanel.yaml`; o reverse proxy aponta para
  `http://127.0.0.1:{config['gateway_port']}`.
- Portainer: importe `stack.portainer.yaml` e informe as variáveis do `.env`.

Os quatro YAMLs são renders planos equivalentes, sem anchors, aliases ou `build`.
Todos os dados ficam em `./volumes`; secrets ficam em `./secrets`.
O diretório `./secrets` usa modo `0700`; os arquivos montados nos containers usam
`0444` para leitura pelos processos non-root e continuam inacessíveis a outros
usuários do host por causa do diretório pai.

O primeiro administrador é criado somente por `bootstrap-admin.sh EMAIL`. A senha
é solicitada sem eco (ou aceita em `PIGE360_BOOTSTRAP_PASSWORD` apenas no processo
corrente), trafega por stdin e não é gravada em `.env`, arquivo ou log.

O perfil opcional `build-farm` não é iniciado por estes comandos e
`BUILD_FARM_ENABLED=false` é o padrão. Só o habilite depois de provisionar e
publicar os agentes Linux/Android (e os runners nativos externos exigidos pelos
demais alvos); a stack administrativa principal não depende desse perfil.

## Operação

```bash
./validate.sh
./healthcheck.sh
./logs.sh pige360-api
./backup.sh
./update.sh {config['tag']}
./rollback.sh TAG_IMUTAVEL
./stop.sh stop
```

{immutable_note}

`backup.sh [DIRETORIO]` suspende os processos first-party que escrevem, exporta
Control Plane, roles e bancos dos tenants, espelha MinIO, arquiva o storage local
e gera `manifest.json` + `SHA256SUMS`. `.env` e secrets ficam em
`configuration/`, separados dos dados. **O backup não é criptografado**: mantenha
o diretório com permissão restrita e aplique criptografia/controle de acesso no
destino externo.

A restauração é fail-closed, valida todos os hashes e exige confirmação explícita:

```bash
./restore.sh /caminho/do/backup --confirm RESTORE-PIGE360
```

Ela não sobrescreve automaticamente `.env` ou `./secrets`. Se estiver recuperando
outro host, restaure primeiro os arquivos de `configuration/`, preserve os modos
`0700`/`0444` e então execute o comando acima. `stop.sh` nunca remove volumes.

## Regerar

Na raiz do fonte:

```bash
python3 scripts/deploy/generate_standalone_deployments.py
python3 scripts/deploy/generate_standalone_deployments.py --check
```
'''.encode("utf-8")


def config_files() -> dict[str, bytes]:
    result = {
        "config/init-minio.sh": (ROOT / "infra/scripts/init-minio.sh").read_bytes(),
        "config/observability/otel-collector.yaml": (ROOT / "infra/monitoring/otel-collector.yaml").read_bytes(),
        "config/observability/prometheus.yml": (ROOT / "infra/monitoring/prometheus.yml").read_bytes(),
        "config/observability/loki.yaml": (ROOT / "infra/monitoring/loki.yaml").read_bytes(),
        "config/observability/alloy.config": (ROOT / "deploy/observability/alloy.config").read_bytes(),
        "config/gateway/default.conf.template": gateway_template(),
        "tools/backup_manifest.py": (ROOT / "scripts/backup/backup_manifest.py").read_bytes(),
    }
    for source_dir, target_dir in (
        (ROOT / "infra/monitoring/grafana/provisioning", "config/observability/grafana/provisioning"),
        (ROOT / "infra/monitoring/grafana/dashboards", "config/observability/grafana/dashboards"),
    ):
        for path in sorted(source_dir.rglob("*")):
            if path.is_file():
                result[f"{target_dir}/{path.relative_to(source_dir).as_posix()}"] = path.read_bytes()
    return result


def expected_files(name: str, config: dict[str, str]) -> dict[str, bytes]:
    _, env_values = parse_env_example(ROOT / ".env.example")
    env_values.update(
        {
            "APP_ENV": config["app_env"],
            "APP_VERSION": config["version"],
            "PIGE360_BASE_DOMAIN": config["base_domain"],
            "PLATFORM_API_HOST": f"api.{config['base_domain']}",
            "PLATFORM_BRANDING_HOST": f"branding.{config['base_domain']}",
            "PLATFORM_CONSOLE_HOST": f"console.{config['base_domain']}",
            "PLATFORM_DOWNLOADS_HOST": f"downloads.{config['base_domain']}",
            "PLATFORM_OPS_HOST": f"ops.{config['base_domain']}",
        }
    )
    compose = render_compose(config, env_values)
    result = {
        ".env.example": render_env(config),
        "compose.yaml": compose,
        "compose.dockge.yaml": compose,
        "compose.cloudpanel.yaml": compose,
        "stack.portainer.yaml": compose,
        "README.md": readme(config),
        **operational_scripts(config),
        **config_files(),
    }
    manifest = {
        "schema_version": 1,
        "generator": "scripts/deploy/generate_standalone_deployments.py",
        "environment": name,
        "project_name": config["project"],
        "image_registry": "ghcr.io/wkarts",
        "image_tag": config["tag"],
        "mode": "image-only",
        "files": {path: sha256(data) for path, data in sorted(result.items())},
    }
    result["GENERATED-MANIFEST.json"] = (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    return result


def platform_files(
    environment: str,
    platform: str,
    config: dict[str, str],
    environment_files: dict[str, bytes],
) -> dict[str, bytes]:
    excluded = {
        "GENERATED-MANIFEST.json",
        "compose.dockge.yaml",
        "compose.cloudpanel.yaml",
        "stack.portainer.yaml",
    }
    result = {path: data for path, data in environment_files.items() if path not in excluded}
    compose = environment_files["compose.yaml"]
    if platform == "portainer":
        result["stack.yaml"] = compose
    result["PLATFORM.md"] = (
        f"# PIGE360 {environment} no {platform.capitalize()}\n\n"
        f"Este diretório é o render standalone para {platform}. "
        "O `compose.yaml` local é usado pelos scripts operacionais. "
        + ("Na interface do Portainer importe `stack.yaml`.\n" if platform == "portainer" else "Importe `compose.yaml`.\n")
    ).encode("utf-8")
    manifest = {
        "schema_version": 1,
        "generator": "scripts/deploy/generate_standalone_deployments.py",
        "environment": environment,
        "platform": platform,
        "project_name": config["project"],
        "image_registry": "ghcr.io/wkarts",
        "image_tag": config["tag"],
        "mode": "image-only",
        "files": {path: sha256(data) for path, data in sorted(result.items())},
    }
    result["GENERATED-MANIFEST.json"] = (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    return result


def validate_render(name: str, files: dict[str, bytes]) -> None:
    for required in (
        ".env.example",
        "install.sh",
        "validate.sh",
        "healthcheck.sh",
        "logs.sh",
        "stop.sh",
        "update.sh",
        "rollback.sh",
        "bootstrap-admin.sh",
        "init-secrets.sh",
        "backup.sh",
        "restore.sh",
        "tools/backup_manifest.py",
    ):
        if required not in files:
            raise RuntimeError(f"{name}: arquivo operacional ausente: {required}")
    compose = files["compose.yaml"].decode("utf-8")
    for token in ("build:", "&id", "*id", "<<:"):
        if token in compose:
            raise RuntimeError(f"{name}: token proibido no Compose: {token}")
    parsed = yaml.safe_load(compose)
    if not isinstance(parsed, dict) or not isinstance(parsed.get("services"), dict):
        raise RuntimeError(f"{name}: Compose renderizado inválido")
    services = parsed["services"]
    publishers = [service for service, value in services.items() if isinstance(value, dict) and value.get("ports")]
    if publishers != ["pige360-gateway"]:
        raise RuntimeError(f"{name}: publicadores inesperados: {publishers}")
    for service, image_name in FIRST_PARTY_IMAGES.items():
        definition = services.get(service) or {}
        image = str(definition.get("image", ""))
        if image_name not in image or "ghcr.io/wkarts" not in image:
            raise RuntimeError(f"{name}: imagem first-party inválida em {service}: {image}")
        env_files = definition.get("env_file") or []
        if isinstance(env_files, str):
            env_files = [env_files]
        if "./.env" not in env_files:
            raise RuntimeError(f"{name}: env_file ./.env ausente em {service}")
    for service, definition in services.items():
        if not isinstance(definition, dict):
            continue
        logging = definition.get("logging") or {}
        options = logging.get("options") or {} if isinstance(logging, dict) else {}
        if logging.get("driver") != "json-file" or str(options.get("max-size")) != "20m" or str(options.get("max-file")) != "5":
            raise RuntimeError(f"{name}: política json-file ausente em {service}")
    volume_init = services.get("pige360-volume-init") or {}
    if "pige360-volume-init" in (volume_init.get("depends_on") or {}):
        raise RuntimeError(f"{name}: ciclo próprio em pige360-volume-init")
    if parsed.get("volumes"):
        raise RuntimeError(f"{name}: volumes nomeados ainda presentes")
    if any(isinstance(key, str) and key.startswith("x-") for key in parsed):
        raise RuntimeError(f"{name}: extensão x-* ainda presente")


def write_target(target: Path, files: dict[str, bytes], *, check: bool) -> list[str]:
    errors: list[str] = []
    for relative, data in sorted(files.items()):
        path = target / relative
        if check:
            if not path.is_file():
                errors.append(f"ausente: {path.relative_to(ROOT)}")
            elif path.read_bytes() != data:
                errors.append(f"divergente: {path.relative_to(ROOT)}")
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.is_file() or path.read_bytes() != data:
            path.write_bytes(data)
        mode = GENERATED_MODES.get(path.name, 0o644)
        os.chmod(path, mode)
    return errors


# ---------------------------------------------------------------------------
# Render service-native (1.1.2)
#
# O código acima permanece temporariamente como leitor compatível do formato
# 1.1.1. As definições abaixo substituem somente a saída operacional: nenhum
# script ou arquivo de configuração do host é necessário para subir o stack.
# ---------------------------------------------------------------------------

_render_env_legacy = render_env

OPS_IMAGE = "pige360-ops"
OPS_SERVICES = {
    "pige360-secrets-init",
    "pige360-config-init",
    "pige360-data-init",
    "pige360-config-validate",
    "pige360-migrations-control",
    "pige360-migrations-tenants",
    "pige360-readiness",
    "pige360-bootstrap-admin",
    "pige360-secret-set",
    "pige360-backup",
    "pige360-restore",
    "pige360-diagnostics",
}
SERVICE_VOLUMES = {
    "pige360-secrets": {},
    "pige360-config": {},
    "pige360-operations": {},
    "pige360-backups": {},
}
CONFIG_TARGETS = {
    "pige360-minio-init": "/opt/pige360/config/init-minio.sh",
    "pige360-otel-collector": "/opt/pige360/config/observability/otel-collector.yaml",
    "pige360-prometheus": "/opt/pige360/config/observability/prometheus.yml",
    "pige360-loki": "/opt/pige360/config/observability/loki.yaml",
    "pige360-alloy": "/opt/pige360/config/observability/alloy.config",
}


def _ops_image(config: dict[str, str]) -> str:
    return (
        "${PIGE360_IMAGE_REGISTRY:-ghcr.io/wkarts}/pige360-ops:"
        f"${{PIGE360_IMAGE_TAG:-{config['tag']}}}"
    )


def _log_policy() -> dict[str, Any]:
    return {"driver": "json-file", "options": {"max-size": "20m", "max-file": "5"}}


def _volume_mount(service: dict[str, Any], mount: str) -> None:
    volumes = service.setdefault("volumes", [])
    if mount not in volumes:
        volumes.append(mount)


def _dependency(service: dict[str, Any], name: str, condition: str) -> None:
    depends = service.setdefault("depends_on", {})
    if isinstance(depends, list):
        depends = {item: {"condition": "service_started"} for item in depends}
        service["depends_on"] = depends
    depends[name] = {"condition": condition}


def _ops_common(config: dict[str, str], *, network: bool = False) -> dict[str, Any]:
    service: dict[str, Any] = {
        "image": _ops_image(config),
        "pull_policy": "always",
        "env_file": ["./.env"],
        "restart": "no",
        "read_only": True,
        "tmpfs": ["/tmp:mode=1777"],
        "security_opt": ["no-new-privileges:true"],
        "logging": _log_policy(),
    }
    service["networks"] = ["pige360-app", "pige360-data"] if network else []
    if not network:
        service["network_mode"] = "none"
        service.pop("networks", None)
    return service


def _ops_services(config: dict[str, str], app_init: dict[str, Any]) -> dict[str, dict[str, Any]]:
    secrets_init = _ops_common(config)
    secrets_init.update(
        {
            "user": "0:0",
            "command": ["init-secrets"],
            "volumes": ["pige360-secrets:/var/lib/pige360/secrets"],
        }
    )
    config_init = _ops_common(config)
    config_init.update(
        {
            "user": "0:0",
            "command": ["init-config"],
            "volumes": ["pige360-config:/var/lib/pige360/config"],
        }
    )
    data_init = _ops_common(config)
    data_init.update(
        {
            "user": "0:0",
            "command": ["init-data"],
            "volumes": [
                "pige360-tenant-storage:/var/lib/pige360/tenants",
                "pige360-operations:/var/lib/pige360/operations",
                "pige360-backups:/var/lib/pige360/backups",
                "pige360-prometheus:/var/lib/pige360/prometheus",
                "pige360-grafana:/var/lib/pige360/grafana",
                "pige360-loki:/var/lib/pige360/loki",
            ],
        }
    )
    validate = _ops_common(config)
    validate.update(
        {
            "command": ["validate"],
            "volumes": [
                "pige360-secrets:/var/lib/pige360/secrets:ro",
                "pige360-config:/var/lib/pige360/config:ro",
            ],
            "depends_on": {
                "pige360-secrets-init": {"condition": "service_completed_successfully"},
                "pige360-config-init": {"condition": "service_completed_successfully"},
                "pige360-data-init": {"condition": "service_completed_successfully"},
            },
        }
    )

    migration_base = copy.deepcopy(app_init)
    migration_base.pop("build", None)
    migration_base.pop("secrets", None)
    migration_base["image"] = _ops_image(config)
    migration_base["pull_policy"] = "always"
    migration_base["env_file"] = ["./.env"]
    migration_environment = migration_base.setdefault("environment", {})
    migration_environment["APP_ENV"] = "${APP_ENV}"
    migration_environment["APP_VERSION"] = "${APP_VERSION}"
    migration_base["restart"] = "no"
    migration_base["read_only"] = True
    migration_base["tmpfs"] = ["/tmp:mode=1777"]
    migration_base["security_opt"] = ["no-new-privileges:true"]
    migration_base["logging"] = _log_policy()
    migration_base["volumes"] = [
        "pige360-secrets:/run/secrets:ro",
        "pige360-tenant-storage:/var/lib/pige360/tenants",
    ]
    migration_base["depends_on"] = {
        "pige360-config-validate": {"condition": "service_completed_successfully"},
        "pige360-postgres-control": {"condition": "service_healthy"},
        "pige360-postgres-tenants": {"condition": "service_healthy"},
        "pige360-minio-init": {"condition": "service_completed_successfully"},
    }
    control = copy.deepcopy(migration_base)
    control["command"] = ["migrate-control"]
    tenants = copy.deepcopy(migration_base)
    tenants["command"] = ["migrate-tenants"]
    tenants["depends_on"]["pige360-migrations-control"] = {
        "condition": "service_completed_successfully"
    }

    runtime_volumes = [
        "pige360-secrets:/run/secrets:ro",
        "pige360-config:/var/lib/pige360/config:ro",
        "pige360-operations:/var/lib/pige360/operations",
    ]
    on_demand: dict[str, dict[str, Any]] = {}
    for name, command in (
        ("pige360-readiness", ["readiness"]),
        ("pige360-bootstrap-admin", ["bootstrap-admin"]),
        ("pige360-secret-set", ["secret-set"]),
        ("pige360-diagnostics", ["diagnostics"]),
    ):
        service = _ops_common(config, network=True)
        service.update({"profiles": ["operations"], "command": command, "volumes": list(runtime_volumes)})
        on_demand[name] = service
    on_demand["pige360-readiness"]["depends_on"] = {
        "pige360-gateway": {"condition": "service_healthy"}
    }
    on_demand["pige360-bootstrap-admin"]["depends_on"] = {
        "pige360-api": {"condition": "service_healthy"}
    }
    on_demand["pige360-secret-set"]["network_mode"] = "none"
    on_demand["pige360-secret-set"].pop("networks", None)
    on_demand["pige360-secret-set"]["volumes"] = ["pige360-secrets:/var/lib/pige360/secrets"]

    backup = _ops_common(config, network=True)
    backup.update(
        {
            "profiles": ["operations"],
            "command": ["backup"],
            "volumes": runtime_volumes
            + [
                "pige360-backups:/var/lib/pige360/backups",
                "pige360-tenant-storage:/var/lib/pige360/tenants:ro",
            ],
            "depends_on": {"pige360-api": {"condition": "service_healthy"}},
        }
    )
    restore = copy.deepcopy(backup)
    restore["command"] = ["restore"]
    restore["volumes"] = [
        "pige360-secrets:/run/secrets:ro",
        "pige360-config:/var/lib/pige360/config:ro",
        "pige360-operations:/var/lib/pige360/operations",
        "pige360-backups:/var/lib/pige360/backups:ro",
        "pige360-tenant-storage:/var/lib/pige360/tenants",
    ]
    restore["depends_on"] = {
        "pige360-postgres-control": {"condition": "service_healthy"},
        "pige360-postgres-tenants": {"condition": "service_healthy"},
        "pige360-minio": {"condition": "service_healthy"},
    }
    on_demand["pige360-backup"] = backup
    on_demand["pige360-restore"] = restore
    return {
        "pige360-secrets-init": secrets_init,
        "pige360-config-init": config_init,
        "pige360-data-init": data_init,
        "pige360-config-validate": validate,
        "pige360-migrations-control": control,
        "pige360-migrations-tenants": tenants,
        **on_demand,
    }


def _rewrite_service_mounts(name: str, service: dict[str, Any]) -> None:
    original = service.get("volumes") or []
    mounts: list[str] = []
    for raw in original:
        if not isinstance(raw, str):
            continue
        source = raw.split(":", 1)[0]
        if source.startswith("./infra/") or source.startswith("./deploy/"):
            continue
        if source == "." or source.startswith("${ANDROID_SDK_HOME:-"):
            continue
        mounts.append(raw)
    service["volumes"] = mounts
    if service.pop("secrets", None) is not None:
        _volume_mount(service, "pige360-secrets:/run/secrets:ro")
        _dependency(service, "pige360-secrets-init", "service_completed_successfully")
    if name in CONFIG_TARGETS or name == "pige360-grafana":
        _volume_mount(service, "pige360-config:/opt/pige360/config:ro")
        _dependency(service, "pige360-config-init", "service_completed_successfully")
    if name == "pige360-minio-init":
        service["entrypoint"] = ["/bin/sh", "/opt/pige360/config/init-minio.sh"]
    elif name == "pige360-otel-collector":
        service["command"] = ["--config=/opt/pige360/config/observability/otel-collector.yaml"]
    elif name == "pige360-prometheus":
        service["command"] = [
            "--config.file=/opt/pige360/config/observability/prometheus.yml",
            "--storage.tsdb.path=/prometheus",
        ]
    elif name == "pige360-loki":
        service["command"] = ["-config.file=/opt/pige360/config/observability/loki.yaml"]
    elif name == "pige360-alloy":
        service["command"] = [
            "run",
            "--server.http.listen-addr=0.0.0.0:12345",
            "/opt/pige360/config/observability/alloy.config",
        ]
    elif name == "pige360-grafana":
        environment = service.setdefault("environment", {})
        environment["GF_PATHS_PROVISIONING"] = "/opt/pige360/config/observability/grafana/provisioning"


def gateway_service(environment: dict[str, str]) -> dict[str, Any]:
    service = {
        "image": "${GATEWAY_IMAGE:-nginx:1.27.5-alpine}",
        "pull_policy": "missing",
        "depends_on": {
            "pige360-api": {"condition": "service_healthy"},
            "pige360-web": {"condition": "service_healthy"},
            "pige360-platform-console": {"condition": "service_healthy"},
            "pige360-branding-studio": {"condition": "service_healthy"},
            "pige360-tenant-download-center": {"condition": "service_healthy"},
            "pige360-config-init": {"condition": "service_completed_successfully"},
        },
        "environment": {
            "NGINX_ENVSUBST_TEMPLATE_DIR": "/opt/pige360/config/gateway",
            "PIGE360_BASE_DOMAIN": env_expression("PIGE360_BASE_DOMAIN", environment),
            "PLATFORM_API_HOST": env_expression("PLATFORM_API_HOST", environment),
            "PLATFORM_BRANDING_HOST": env_expression("PLATFORM_BRANDING_HOST", environment),
            "PLATFORM_CONSOLE_HOST": env_expression("PLATFORM_CONSOLE_HOST", environment),
            "PLATFORM_DOWNLOADS_HOST": env_expression("PLATFORM_DOWNLOADS_HOST", environment),
            "PLATFORM_OPS_HOST": env_expression("PLATFORM_OPS_HOST", environment),
        },
        "ports": ["${GATEWAY_BIND_HOST:-127.0.0.1}:${GATEWAY_PORT:-58080}:8080"],
        "volumes": ["pige360-config:/opt/pige360/config:ro"],
        "healthcheck": {
            "test": ["CMD-SHELL", "wget -q --spider http://127.0.0.1:8080/healthz"],
            "interval": "15s",
            "timeout": "5s",
            "retries": 20,
            "start_period": "10s",
        },
        "networks": ["pige360-app", "pige360-observability"],
        "restart": "unless-stopped",
        "read_only": True,
        "tmpfs": [
            "/etc/nginx/conf.d:mode=0755",
            "/var/cache/nginx:mode=0755",
            "/var/run:mode=0755",
            "/tmp:mode=1777",
        ],
        "security_opt": ["no-new-privileges:true"],
        "logging": _log_policy(),
    }
    return service


def render_compose(config: dict[str, str], env_values: dict[str, str]) -> bytes:
    document = merge(load_yaml(ROOT / "compose.yaml"), load_yaml(ROOT / "compose.production.yaml"))
    document = merge(document, load_yaml(ROOT / "deploy/compose/compose.logging.yaml"))
    document["name"] = f"${{COMPOSE_PROJECT_NAME:-{config['project']}}}"
    for key in list(document):
        if isinstance(key, str) and key.startswith("x-"):
            document.pop(key)
    services = document.get("services")
    if not isinstance(services, dict):
        raise RuntimeError("Compose canônico sem services")
    app_init = copy.deepcopy(services.pop("pige360-app-init"))
    for name, service in services.items():
        if not isinstance(service, dict):
            raise RuntimeError(f"Serviço inválido: {name}")
        service.pop("build", None)
        service.pop("ports", None)
        service["logging"] = _log_policy()
        if name in FIRST_PARTY_IMAGES:
            image_name = FIRST_PARTY_IMAGES[name]
            service["image"] = (
                f"${{PIGE360_IMAGE_REGISTRY:-ghcr.io/wkarts}}/{image_name}:"
                f"${{PIGE360_IMAGE_TAG:-{config['tag']}}}"
            )
            service["pull_policy"] = "always"
        elif name.startswith("pige360-worker-"):
            service["image"] = (
                "${PIGE360_IMAGE_REGISTRY:-ghcr.io/wkarts}/pige360-worker:"
                f"${{PIGE360_IMAGE_TAG:-{config['tag']}}}"
            )
            service["pull_policy"] = "always"
        if application_service(name):
            service["env_file"] = ["./.env"]
            environment = service.get("environment")
            if isinstance(environment, dict):
                environment["APP_ENV"] = env_expression("APP_ENV", env_values)
                environment["APP_VERSION"] = env_expression("APP_VERSION", env_values)
                for env_key in APP_CONFIG_KEYS:
                    environment.setdefault(env_key, env_expression(env_key, env_values))
        _rewrite_service_mounts(name, service)
        if any(
            isinstance(mount, str) and mount.startswith("pige360-tenant-storage:")
            for mount in service.get("volumes") or []
        ):
            _dependency(service, "pige360-data-init", "service_completed_successfully")
        if name in {
            "pige360-web",
            "pige360-platform-console",
            "pige360-branding-studio",
            "pige360-tenant-download-center",
        }:
            service["healthcheck"] = {
                "test": ["CMD-SHELL", "wget -q --spider http://127.0.0.1:8080/healthz"],
                "interval": "15s",
                "timeout": "5s",
                "retries": 12,
                "start_period": "10s",
            }
        if name.startswith("pige360-worker-"):
            command = service.get("command")
            if isinstance(command, list) and not any(str(item).startswith("--concurrency") for item in command):
                command.extend(["--concurrency=${PIGE360_WORKER_CONCURRENCY:-1}", "--without-gossip", "--without-mingle"])
        if name == "pige360-otel-collector":
            service["profiles"] = ["otel"]

    ops = _ops_services(config, app_init)
    ordered: dict[str, Any] = {}
    for name in ("pige360-secrets-init", "pige360-config-init", "pige360-data-init", "pige360-config-validate"):
        ordered[name] = ops.pop(name)
    for name, service in services.items():
        ordered[name] = service
        if name == "pige360-minio-init":
            ordered["pige360-migrations-control"] = ops.pop("pige360-migrations-control")
            ordered["pige360-migrations-tenants"] = ops.pop("pige360-migrations-tenants")
    ordered["pige360-gateway"] = gateway_service(env_values)
    ordered.update(ops)
    services = document["services"] = ordered

    for name, service in services.items():
        if not isinstance(service, dict):
            continue
        depends = service.get("depends_on")
        if isinstance(depends, dict) and "pige360-app-init" in depends:
            depends.pop("pige360-app-init")
            depends["pige360-migrations-tenants"] = {"condition": "service_completed_successfully"}

    networks = document.get("networks") or {}
    for network in networks.values():
        if isinstance(network, dict):
            network.pop("name", None)
    volumes = document.setdefault("volumes", {})
    for definition in volumes.values():
        if isinstance(definition, dict):
            definition.pop("name", None)
    volumes.update(copy.deepcopy(SERVICE_VOLUMES))
    document.pop("secrets", None)
    rendered = yaml.dump(
        document,
        Dumper=NoAliasDumper,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
        width=120,
    )
    return (
        "# Gerado por scripts/deploy/generate_standalone_deployments.py.\n"
        "# Deployment service-native: requer somente este YAML e um arquivo .env.\n"
        f"# Ambiente: {config['description']}.\n\n{rendered}"
    ).encode("utf-8")


def render_env(config: dict[str, str]) -> bytes:
    rendered = _render_env_legacy(config).decode("utf-8")
    lines = [
        line
        for line in rendered.splitlines()
        if not line.startswith(("PIGE360_SECRETS_DIR=", "PIGE360_DATA_ROOT="))
    ]
    additions = {
        "PIGE360_DEPLOY_TARGET": "base",
        "PIGE360_READINESS_ATTEMPTS": "60",
        "PIGE360_READINESS_DELAY_SECONDS": "5",
        "PIGE360_RESTORE_MAINTENANCE": "",
    }
    for key, value in additions.items():
        replace_env_line(lines, key, value)
    return ("\n".join(lines).rstrip() + "\n").encode("utf-8")


def service_native_readme(config: dict[str, str]) -> bytes:
    environment = "homologação/develop" if config["tag"] == "develop" else "produção"
    text = f"""# PIGE360 {config['version']} — {environment}

Este pacote é **service-native**: para iniciar o PIGE360 são necessários somente
`compose.yaml` e `.env`. Configurações, secrets, migrations e volumes são
preparados por serviços idempotentes do próprio stack.

## Iniciar

```bash
cp .env.example .env
# revise domínio, portas, integrações e tag antes de continuar
docker compose --env-file .env config --quiet
docker compose --env-file .env pull
docker compose --env-file .env up -d --wait
docker compose --env-file .env --profile operations run --rm pige360-readiness readiness
```

O modo `{config['tag']}` usa por padrão
`ghcr.io/wkarts/*:{config['tag']}`. Em produção, `PIGE360_IMAGE_TAG` deve ser
exatamente igual ao `APP_VERSION` SemVer.

## Administração

```bash
# criar o primeiro administrador (senha pelo stdin, sem argumento/process list)
printf '%s' 'SENHA_FORTE' | docker compose --env-file .env --profile operations run --rm -T \
  pige360-bootstrap-admin bootstrap-admin --email admin@exemplo.com

# configurar integração externa
printf '%s' 'TOKEN' | docker compose --env-file .env --profile operations run --rm -T \
  pige360-secret-set secret-set cloudflare_api_token

# diagnóstico e backup
docker compose --env-file .env --profile operations run --rm pige360-diagnostics diagnostics
docker compose --env-file .env --profile operations run --rm pige360-backup backup --name pre-atualizacao
```

Para restore, pare API, gateway, workers e beat; defina temporariamente
`PIGE360_RESTORE_MAINTENANCE=RESTORE-PIGE360`; então execute:

```bash
docker compose --env-file .env --profile operations run --rm \
  pige360-restore restore --name NOME --confirm RESTORE-PIGE360
```

Atualizações de imagem continuam sob controle do Dockge, Portainer ou CI/CD.
Nenhum serviço administrativo recebe acesso ao socket Docker. O Alloy mantém
somente a montagem read-only necessária à descoberta de logs.

## Serviços automáticos

- `pige360-secrets-init`: cria e preserva secrets internos no volume nomeado.
- `pige360-config-init`: materializa gateway e observabilidade a partir da imagem.
- `pige360-data-init`: prepara ownership dos volumes persistentes.
- `pige360-config-validate`: bloqueia configuração/tag inválida antes das migrations.
- `pige360-migrations-control`: atualiza o Control Plane.
- `pige360-migrations-tenants`: atualiza todos os tenants elegíveis.
- `pige360-readiness`: acceptance test executável sob o profile `operations`.
- `pige360-backup`/`pige360-restore`: operação transacional em volume dedicado.
"""
    return text.encode("utf-8")


def _with_manifest(environment: str, platform: str | None, config: dict[str, str], files: dict[str, bytes]) -> dict[str, bytes]:
    manifest = {
        "schema_version": 2,
        "generator": "scripts/deploy/generate_standalone_deployments.py",
        "environment": environment,
        "platform": platform,
        "project_name": config["project"],
        "image_registry": "ghcr.io/wkarts",
        "image_tag": config["tag"],
        "mode": "service-native-image-only",
        "files": {path: sha256(data) for path, data in sorted(files.items())},
    }
    result = dict(files)
    result["GENERATED-MANIFEST.json"] = (
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    sums = "".join(f"{sha256(data)}  {path}\n" for path, data in sorted(result.items()))
    result["SHA256SUMS"] = sums.encode("utf-8")
    return result


def expected_files(name: str, config: dict[str, str]) -> dict[str, bytes]:
    _, env_values = parse_env_example(ROOT / ".env.example")
    env_values.update(
        {
            "APP_ENV": config["app_env"],
            "APP_VERSION": config["version"],
            "PIGE360_BASE_DOMAIN": config["base_domain"],
            "PLATFORM_API_HOST": f"api.{config['base_domain']}",
            "PLATFORM_BRANDING_HOST": f"branding.{config['base_domain']}",
            "PLATFORM_CONSOLE_HOST": f"console.{config['base_domain']}",
            "PLATFORM_DOWNLOADS_HOST": f"downloads.{config['base_domain']}",
            "PLATFORM_OPS_HOST": f"ops.{config['base_domain']}",
        }
    )
    files = {
        ".env.example": render_env(config),
        "compose.yaml": render_compose(config, env_values),
        "README.md": service_native_readme(config),
    }
    return _with_manifest(name, None, config, files)


def platform_files(environment: str, platform: str, config: dict[str, str], environment_files: dict[str, bytes]) -> dict[str, bytes]:
    compose_name = "stack.yaml" if platform == "portainer" else "compose.yaml"
    files = {
        ".env.example": environment_files[".env.example"],
        compose_name: environment_files["compose.yaml"],
        "README.md": environment_files["README.md"],
        "PLATFORM.md": (
            f"# PIGE360 {environment} no {platform.capitalize()}\n\n"
            f"Importe `{compose_name}`, copie as variáveis de `.env.example` e mantenha o projeto "
            "com nome estável. Todo o ciclo de inicialização é executado pelos services do stack.\n"
        ).encode("utf-8"),
    }
    return _with_manifest(environment, platform, config, files)


def validate_render(name: str, files: dict[str, bytes]) -> None:
    compose_key = "compose.yaml" if "compose.yaml" in files else "stack.yaml"
    for required in (".env.example", compose_key, "README.md", "GENERATED-MANIFEST.json", "SHA256SUMS"):
        if required not in files:
            raise RuntimeError(f"{name}: arquivo ausente: {required}")
    if any(path.endswith(".sh") or path.startswith(("config/", "tools/", "secrets/", "volumes/")) for path in files):
        raise RuntimeError(f"{name}: pacote ainda contém suporte de host")
    compose = files[compose_key].decode("utf-8")
    for token in ("build:", "&id", "*id", "<<:", "./config", "./secrets", "./volumes"):
        if token in compose:
            raise RuntimeError(f"{name}: token proibido no Compose: {token}")
    parsed = yaml.safe_load(compose)
    if not isinstance(parsed, dict) or not isinstance(parsed.get("services"), dict):
        raise RuntimeError(f"{name}: Compose inválido")
    services = parsed["services"]
    missing = sorted(OPS_SERVICES - set(services))
    if missing:
        raise RuntimeError(f"{name}: services operacionais ausentes: {missing}")
    publishers = [service for service, value in services.items() if isinstance(value, dict) and value.get("ports")]
    if publishers != ["pige360-gateway"]:
        raise RuntimeError(f"{name}: publicadores inesperados: {publishers}")
    if "pige360-app-init" in services:
        raise RuntimeError(f"{name}: init monolítico legado ainda presente")
    volumes = parsed.get("volumes") or {}
    for required_volume in SERVICE_VOLUMES:
        if required_volume not in volumes:
            raise RuntimeError(f"{name}: volume operacional ausente: {required_volume}")
    for volume_name, definition in volumes.items():
        if isinstance(definition, dict) and "name" in definition:
            raise RuntimeError(f"{name}: volume global não isolado: {volume_name}")
    for service_name, definition in services.items():
        if not isinstance(definition, dict):
            continue
        for mount in definition.get("volumes") or []:
            if isinstance(mount, str) and mount.startswith("./"):
                raise RuntimeError(f"{name}: bind mount relativo em {service_name}: {mount}")
        logging = definition.get("logging") or {}
        options = logging.get("options") or {} if isinstance(logging, dict) else {}
        if logging.get("driver") != "json-file" or str(options.get("max-size")) != "20m" or str(options.get("max-file")) != "5":
            raise RuntimeError(f"{name}: logging limitado ausente em {service_name}")


def write_target(target: Path, files: dict[str, bytes], *, check: bool) -> list[str]:
    errors: list[str] = []
    actual = {
        path.relative_to(target).as_posix()
        for path in target.rglob("*")
        if path.is_file() or path.is_symlink()
    } if target.exists() else set()
    expected = set(files)
    for stale in sorted(actual - expected):
        path = target / stale
        if check:
            errors.append(f"inesperado: {path.relative_to(ROOT)}")
        elif path.is_symlink() or path.is_file():
            path.unlink()
    if not check and target.exists():
        for directory in sorted((p for p in target.rglob("*") if p.is_dir()), reverse=True):
            try:
                directory.rmdir()
            except OSError:
                pass
    for relative, data in sorted(files.items()):
        path = target / relative
        if check:
            if not path.is_file():
                errors.append(f"ausente: {path.relative_to(ROOT)}")
            elif path.read_bytes() != data:
                errors.append(f"divergente: {path.relative_to(ROOT)}")
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.is_file() or path.read_bytes() != data:
            path.write_bytes(data)
        os.chmod(path, 0o644)
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="falha se os renders versionados estiverem desatualizados")
    args = parser.parse_args()
    errors: list[str] = []
    for name, config in ENVIRONMENTS.items():
        files = expected_files(name, config)
        validate_render(name, files)
        errors.extend(write_target(DEPLOYMENTS / name, files, check=args.check))
        for platform in ("dockge", "cloudpanel", "portainer"):
            rendered = platform_files(name, platform, config, files)
            validate_render(f"{platform}/{name}", rendered)
            errors.extend(write_target(DEPLOYMENTS / platform / name, rendered, check=args.check))
    if errors:
        print("STANDALONE_DEPLOYMENTS=FAIL")
        for error in errors:
            print(f"- {error}")
        return 1
    print("STANDALONE_DEPLOYMENTS=PASS")
    print(f"ENVIRONMENTS={len(ENVIRONMENTS)}")
    print("IMAGE_REGISTRY=ghcr.io/wkarts")
    print("PUBLISHED_SERVICE=pige360-gateway")
    print("MODE=image-only")
    return 0


if __name__ == "__main__":
    sys.exit(main())
