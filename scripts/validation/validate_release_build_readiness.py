#!/usr/bin/env python3
"""Valida a release coordenada multiplataforma e o deploy canônico do PIGE360."""

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
        "release_tag:",
        "allow_partial_release:",
        "compute-next-version.mjs",
        "persist_version:",
        "deployer_agent:",
        "deployer_desktop:",
        "desktop:",
        "web_pwa:",
        "cloudpanel:",
        "android:",
        "ios:",
        "release_bundle:",
        "publish:",
        "sync_develop:",
        "package-web-pwa.sh",
        "package-local.sh --output-dir release/output",
        "scripts/desktop/build-all.sh",
        "scripts/mobile/build-android.sh",
        "scripts/mobile/build-ios.sh",
        "collect-release-assets.mjs",
        "enforce-release-policy.mjs",
        "write-build-status.mjs",
        "--draft",
        "PIGE360_REQUIRE_LOCKED",
        "prerelease_id=",
        "--prerelease",
        'test "$manifest_count" -eq 13',
        "cargo metadata --manifest-path rust/Cargo.toml --locked",
        "--allow-prerelease",
    ):
        if required not in release:
            failures.append(f"release coordenada sem requisito: {required}")

    for target_id in (
        "desktop-windows-x64",
        "desktop-windows-x86",
        "desktop-linux-x64",
        "desktop-linux-arm64",
        "desktop-macos-x64",
        "desktop-macos-arm64",
        "web-pwa",
        "cloudpanel-linux-x64",
        "cloudpanel-linux-x86",
        "android-arm64-apk",
        "android-aab",
        "ios-arm64-unsigned-ipa",
        "deployer-agent-linux-x64",
        "deployer-windows-x64",
        "deployer-linux-x64",
        "deployer-macos-x64",
    ):
        if target_id not in release:
            failures.append(f"alvo obrigatório ausente da release: {target_id}")

    collector = read("scripts/release/collect-release-assets.mjs")
    for extension in (".apk", ".aab", ".ipa", ".dmg", ".msi", ".exe", ".AppImage", ".deb", ".rpm", ".tar.gz"):
        if extension not in collector:
            failures.append(f"coletor não aceita artefato final: {extension}")
    if "includes('target')" not in collector or "Cargo target não pode ser publicado" not in collector:
        failures.append("coletor não bloqueia publicação acidental do diretório Cargo target")
    for required in (
        "requiredAssets",
        "allowedSuffixes",
        "count: 13",
        "count: 7",
        "count: 5",
        "Tipo de artefato inesperado",
        "Contexto de artefato desconhecido",
        "CORE_STATIC_ASSETS",
        "CORE_VERSIONED_SUFFIXES",
        ".pige360-delivery-root.json",
    ):
        if required not in collector:
            failures.append(f"coletor não valida tipo/quantidade de artefato final: {required}")

    pwa_packager = read("scripts/release/package-web-pwa.sh")
    for required in ("scripts/validation/validate_pwa_builds.py", 'unzip -tq "$archive"'):
        if required not in pwa_packager:
            failures.append(f"pacote Web/PWA não valida o artefato gerado: {required}")

    version_validator = read("scripts/validation/validate_version_consistency.py")
    for required in ("--allow-prerelease", "is_valid_version", "stable_semver"):
        if required not in version_validator:
            failures.append(f"validador de versão não preserva stable e prerelease explícito: {required}")
    ci_runner = read("scripts/ci/run_all.py")
    if "--allow-prerelease" not in ci_runner or "version_command.append('--allow-prerelease')" not in ci_runner:
        failures.append("CI integral não encaminha o gate explícito de prerelease")

    for workflow_path in (
        ".github/workflows/31-build-desktop.yml",
        ".github/workflows/32-build-android.yml",
        ".github/workflows/33-build-ios.yml",
        ".github/workflows/35-build-deployer.yml",
    ):
        workflow_triggers = triggers(workflow_path)
        if "workflow_dispatch" not in workflow_triggers:
            failures.append(f"workflow nativo não é executável manualmente: {workflow_path}")
        if "pull_request" not in workflow_triggers:
            failures.append(f"workflow nativo não valida Pull Requests: {workflow_path}")
        if "push" in workflow_triggers:
            failures.append(f"workflow nativo possui push independente da release: {workflow_path}")

    android_workflow = read(".github/workflows/32-build-android.yml")
    if "inputs.sign && inputs.scope != 'all'" not in android_workflow:
        failures.append("workflow Android ignora solicitação de assinatura fora da matriz completa")
    ios_workflow = read(".github/workflows/33-build-ios.yml")
    for required in (
        "build_mode=local-signing",
        "requested_mode=store",
        "inputs.sign && steps.sign.outcome != 'success'",
        "scripts/mobile/sign-ios.sh",
    ):
        if required not in ios_workflow:
            failures.append(f"workflow iOS não separa build unsigned da assinatura condicional: {required}")
    tenant_workflow = read(".github/workflows/34-build-tenant-apps.yml")
    for required in (
        "if: ${{ inputs.publish_stores == true }}",
        "REMOTE_RELEASE_ENABLED",
        "exit 78",
    ):
        if required not in tenant_workflow:
            failures.append(f"workflow white-label mascara solicitação de publicação: {required}")

    for workflow_name in (
        "31-build-desktop.yml",
        "32-build-android.yml",
        "33-build-ios.yml",
        "34-build-tenant-apps.yml",
        "35-build-deployer.yml",
        "36-develop-prerelease.yml",
        "50-release.yml",
        "51-recover-release.yml",
    ):
        canonical = read(f".github/workflows/{workflow_name}")
        mirrored = read(f"CI_CD_KIT_LOCAL/workflows/{workflow_name}")
        if canonical != mirrored:
            failures.append(f"workflow {workflow_name} diverge do espelho CI_CD_KIT_LOCAL")

    recovery = read(".github/workflows/51-recover-release.yml")
    for required in (
        "release_tag:",
        "source_run_id:",
        "allow_partial_release:",
        "rust/Cargo.lock",
        "manifest_count",
        '"$manifest_count" -eq 13',
        "gh workflow run 50-release.yml",
        "O workflow 50 reconstruirá os 16 alvos a partir da tag exata.",
        "Nenhum artefato de execução anterior foi publicado ou reaproveitado.",
        "prerelease_id=",
        'GITHUB_REF" = \'refs/heads/main\'',
    ):
        if required not in recovery:
            failures.append(f"retomada de release sem requisito seguro: {required}")
    for forbidden in (
        "actions/download-artifact",
        "publish-github-release.sh",
        "gh release create",
        "gh release upload",
    ):
        if forbidden in recovery:
            failures.append(f"retomada de release reutiliza/publica artefato diretamente: {forbidden}")

    for script_path in (
        "scripts/desktop/build-all.sh",
        "scripts/mobile/build-android.sh",
        "scripts/mobile/build-ios.sh",
        "scripts/release/package-web-pwa.sh",
    ):
        script = read(script_path)
        has_strict_semver = (
            "prerelease_id=" in script and "semver_re=" in script
        ) or (
            script_path == "scripts/mobile/build-ios.sh"
            and "re.fullmatch(" in script
            and "[0-9A-Za-z-]" in script
        )
        if not has_strict_semver:
            failures.append(f"empacotador não aceita SemVer stable/prerelease: {script_path}")

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
        "HostRegexp(`^[a-z0-9-]+\\.${TENANT_DEFAULT_BASE_DOMAIN:-pige360.com.br}$`)",
        "PathPrefix(`/api`)",
        "PIGE360_TRAEFIK_DYNAMIC_DIR_INTERNAL",
        "pige360-traefik-dynamic",
        "pige360-edge-init",
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
