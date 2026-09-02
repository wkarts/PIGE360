#!/usr/bin/env python3
"""Valida o contrato de release Web/Server e o deploy canônico do PIGE360.

Os binários Desktop/Android/iOS estão congelados e são deliberadamente manuais.
Eles não podem bloquear nem compor a distribuição oficial Web/PWA/Server.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def yaml_doc(path: str):
    return yaml.safe_load(read(path))


def triggers(path: str) -> dict:
    document = yaml_doc(path) or {}
    value = document.get("on", document.get(True, {}))
    return value or {}


def main() -> int:
    failures: list[str] = []

    release_path = ".github/workflows/50-release.yml"
    release = read(release_path)
    release_kit = read("CI_CD_KIT_LOCAL/workflows/50-release.yml")
    if release != release_kit:
        failures.append("workflow 50-release diverge do espelho CI_CD_KIT_LOCAL")

    for required in (
        "branches: [main]",
        "force_bump:",
        "compute-next-version.mjs",
        "runtime_images:",
        "web_pwa:",
        "release_bundle:",
        "persist_version:",
        "publish:",
        "sync_develop:",
        "package-web-pwa.sh",
        "package-local.sh --output-dir release/output",
        "publish-github-release.sh release/publish",
        "Bloquear binários mobile/desktop",
        "Release oficial e estável promovida",
    ):
        if required not in release:
            failures.append(f"release Web/Server sem requisito: {required}")

    for forbidden in (
        "scripts/mobile/build-android.sh",
        "scripts/mobile/build-ios.sh",
        "scripts/mobile/sign-android.sh",
        "scripts/mobile/sign-ios.sh",
        "scripts/desktop/build-all.sh",
        "distribution_mode == 'homologation'",
        "distribution_mode == 'store'",
    ):
        if forbidden in release:
            failures.append(f"release oficial ainda acoplada ao legado nativo: {forbidden}")

    for extension in ("*.apk", "*.aab", "*.ipa", "*.dmg", "*.msi", "*.exe", "*.appimage", "*.deb", "*.rpm"):
        if extension not in release.lower():
            failures.append(f"release não bloqueia artefato nativo: {extension}")

    for workflow_path in (
        ".github/workflows/31-build-desktop.yml",
        ".github/workflows/32-build-android.yml",
        ".github/workflows/33-build-ios.yml",
    ):
        workflow_triggers = triggers(workflow_path)
        if "workflow_dispatch" not in workflow_triggers:
            failures.append(f"workflow nativo não é executável manualmente: {workflow_path}")
        if "pull_request" in workflow_triggers or "push" in workflow_triggers:
            failures.append(f"workflow nativo voltou a ter gatilho automático: {workflow_path}")

    web = read(".github/workflows/30-build-web.yml")
    web_kit = read("CI_CD_KIT_LOCAL/workflows/30-build-web.yml")
    try:
        yaml_doc(".github/workflows/30-build-web.yml")
    except yaml.YAMLError as exc:
        failures.append(f"workflow Web/PWA inválido: {exc}")
    if web != web_kit:
        failures.append("workflow 30-build-web diverge do espelho CI_CD_KIT_LOCAL")
    for required in ("pull_request:", "develop", "npm run validate:ts", "npm run build:web", "pige360-web-pwa-${{ github.run_id }}"):
        if required not in web:
            failures.append(f"workflow Web/PWA sem requisito: {required}")

    publisher = read("scripts/release/publish-github-release.sh")
    for required in (
        "Use somente SemVer estável X.Y.Z",
        "asset_source_id",
        "Artefato idêntico deduplicado",
        "Artefato com nome repetido preservado como",
        "RELEASE_TARGET_SHA",
        "versões publicadas são imutáveis",
    ):
        if required not in publisher:
            failures.append(f"publicador estável sem requisito: {required}")

    required_deploy_files = (
        "deploy/README.md",
        "deploy/domains/domain-contract.yaml",
        "deploy/images/catalog.yaml",
        "deploy/provisioning/tenant-contract.yaml",
        "deploy/observability/logging-contract.yaml",
        "deploy/observability/alloy.config",
        "deploy/compose/compose.edge.yaml",
        "deploy/compose/compose.cloudpanel.yaml",
        "deploy/compose/compose.logging.yaml",
        "infra/connect-api/integration.yaml",
    )
    for path in required_deploy_files:
        if not (ROOT / path).is_file():
            failures.append(f"arquivo de deploy canônico ausente: {path}")

    for path in (
        "deploy/domains/domain-contract.yaml",
        "deploy/images/catalog.yaml",
        "deploy/provisioning/tenant-contract.yaml",
        "deploy/observability/logging-contract.yaml",
        "deploy/compose/compose.edge.yaml",
        "deploy/compose/compose.cloudpanel.yaml",
        "deploy/compose/compose.logging.yaml",
        "infra/cloudflare/provider-contract.yaml",
        "infra/connect-api/integration.yaml",
        "infra/monitoring/otel-collector.yaml",
        "compose.production.yaml",
    ):
        try:
            yaml_doc(path)
        except (yaml.YAMLError, OSError) as exc:
            failures.append(f"YAML inválido em {path}: {exc}")

    if (ROOT / "infra/evolution/integration.yaml").exists():
        failures.append("integração legada Evolution continua exposta em infra/evolution")

    domain = yaml_doc("deploy/domains/domain-contract.yaml") or {}
    tenant = domain.get("tenant", {})
    if domain.get("base_domain") != "pige360.com.br":
        failures.append("domínio-base canônico não é pige360.com.br")
    if tenant.get("wildcard") != "*.pige360.com.br":
        failures.append("wildcard canônico *.pige360.com.br ausente")
    if tenant.get("dns_per_tenant_required") is not False:
        failures.append("tenant canônico ainda exige DNS individual")
    reserved = set(domain.get("reserved_slugs", []))
    for slug in {"api", "console", "ops", "www", "admin", "platform"}:
        if slug not in reserved:
            failures.append(f"slug reservado ausente: {slug}")

    edge = read("deploy/compose/compose.edge.yaml")
    for required in (
        "traefik:v3.7.12",
        "dnschallenge.provider=cloudflare",
        "Host(`*.${TENANT_DEFAULT_BASE_DOMAIN:-pige360.com.br}`)",
        "PathPrefix(`/api`)",
        "PLATFORM_CONSOLE_HOST",
        "PLATFORM_API_HOST",
        "PLATFORM_OPS_HOST",
    ):
        if required not in edge:
            failures.append(f"edge multitenant sem requisito: {required}")

    otel = read("infra/monitoring/otel-collector.yaml")
    if "otlphttp/loki" not in otel or "http://pige360-loki:3100/otlp" not in otel:
        failures.append("logs OTLP não são enviados ao Loki")
    alloy = read("deploy/observability/alloy.config")
    if "loki.source.docker" not in alloy or "pige360-loki:3100/loki/api/v1/push" not in alloy:
        failures.append("stdout/stderr Docker não possui coleta Alloy -> Loki")

    connect_api = yaml_doc("infra/connect-api/integration.yaml") or {}
    if connect_api.get("provider") != "connect_api" or connect_api.get("compatibility", {}).get("meta") is not True:
        failures.append("Connect API não está definido como provider Meta-compatible")

    result = {"status": "passed" if not failures else "failed", "failures": failures}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
