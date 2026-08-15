#!/usr/bin/env python3
"""Bloqueia regressões conhecidas na matriz de builds publicável."""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BRIDGED_APPS = {
    "admin-app",
    "desktop-admin",
    "family-app",
    "kiosk-app",
    "pos-app",
    "student-app",
    "teacher-app",
    "timeclock-app",
}
MOBILE_BRIDGED_APPS = {
    "admin-app",
    "family-app",
    "kiosk-app",
    "pos-app",
    "student-app",
    "teacher-app",
    "timeclock-app",
}
COMMANDS = {
    "secure_session_put",
    "secure_session_get",
    "secure_session_delete",
    "offline_initialize",
    "offline_outbox_enqueue",
    "offline_outbox_pending",
    "offline_outbox_apply_result",
    "offline_cache_get",
    "offline_cache_put",
    "fiscal_snapshot_verify",
    "print_enqueue",
    "native_wipe_user",
}


def main() -> int:
    failures: list[str] = []
    bridge = ROOT / "rust/crates/native-bridge/src/lib.rs"
    commands = ROOT / "rust/crates/native-bridge/src/tauri_commands.rs"
    bridge_text = bridge.read_text(encoding="utf-8")
    command_text = commands.read_text(encoding="utf-8") if commands.is_file() else ""

    command_attribute = re.compile(r"^\s*#\[tauri::command\]\s*$", re.MULTILINE)
    if command_attribute.search(bridge_text):
        failures.append("os macros de comando Tauri não podem permanecer na crate bridge externa")
    missing_commands = sorted(command for command in COMMANDS if f"fn {command}" not in command_text)
    if missing_commands:
        failures.append(f"adaptadores Tauri ausentes: {missing_commands}")
    if len(command_attribute.findall(command_text)) != len(COMMANDS):
        failures.append("quantidade de adaptadores Tauri divergente")

    module_path = '#[path = "../../../../rust/crates/native-bridge/src/tauri_commands.rs"]'
    for app in sorted(BRIDGED_APPS):
        main_rs = ROOT / "apps" / app / "src-tauri/src/main.rs"
        command_source = main_rs
        if app in MOBILE_BRIDGED_APPS:
            command_source = main_rs.with_name("lib.rs")
            main_text = main_rs.read_text(encoding="utf-8")
            if "::run();" not in main_text:
                failures.append(f"{app}: executável não delega para a biblioteca móvel")
            if not command_source.is_file():
                failures.append(f"{app}: biblioteca móvel Tauri ausente")
                continue
        text = command_source.read_text(encoding="utf-8")
        if module_path not in text:
            failures.append(f"{app}: módulo local de comandos Tauri ausente")
        stale = [command for command in COMMANDS if f"pige360_native_bridge::{command}" in text]
        if stale:
            failures.append(f"{app}: comandos externos ainda registrados: {sorted(stale)}")
        missing = [command for command in COMMANDS if f"tauri_commands::{command}" not in text]
        if missing:
            failures.append(f"{app}: comandos locais ausentes: {sorted(missing)}")
        if app in MOBILE_BRIDGED_APPS:
            for required in ("#[cfg_attr(mobile, tauri::mobile_entry_point)]", "pub fn run()"):
                if required not in text:
                    failures.append(f"{app}: biblioteca móvel sem ponto de entrada Tauri: {required}")
            cargo_toml = (ROOT / "apps" / app / "src-tauri/Cargo.toml").read_text(encoding="utf-8")
            if "[lib]" not in cargo_toml or 'crate-type = ["staticlib", "cdylib", "rlib"]' not in cargo_toml:
                failures.append(f"{app}: biblioteca móvel não expõe cdylib/staticlib exigida pelo Tauri Android")
            package = json.loads((ROOT / "apps" / app / "package.json").read_text(encoding="utf-8"))
            if package.get("scripts", {}).get("tauri") != "tauri":
                failures.append(f"{app}: script npm tauri ausente para a chamada feita pelo Gradle Android")

    desktop = (ROOT / "scripts/desktop/build-all.sh").read_text(encoding="utf-8")
    for required in (
        'version="$(tr -d',
        'msi_version="${version%-alpha.*}-${version##*.}"',
        '--config "$desktop_tauri_config"',
    ):
        if required not in desktop:
            failures.append(f"build desktop sem conversão verificável da versão alpha para MSI: {required}")

    ios = (ROOT / "scripts/mobile/build-ios.sh").read_text(encoding="utf-8")
    if 'ios_version="${version%-alpha.*}"' not in ios or '--config "$ios_config"' not in ios:
        failures.append("build iOS não converte a versão alpha para CFBundleShortVersionString numérico")
    if 'version="$(tr -d' not in ios:
        failures.append("build iOS não deriva a versão canônica de VERSION")
    for required in ("tauri ios init --ci", "tauri.ios.conf.json", "restore_ios_platform_config", "rm -rf src-tauri/gen/apple", "Falha ao gerar o projeto iOS", "--mode", "local-signing", "PIGE360000", "tauri ios build --target aarch64 --open", "CODE_SIGNING_ALLOWED=NO", "cleanup_tauri_options", "prepare_ios_runtime_config", "restore_ios_runtime_config", "mktemp -d", "zip -qry", "verify_local_signing_ipa", "lipo -archs", "Payload", "ready-for-local-signing"):
        if required not in ios:
            failures.append(f"build iOS sem geração verificável do projeto Apple: {required}")

    android = (ROOT / "scripts/mobile/build-android.sh").read_text(encoding="utf-8")
    for required in ("NDK_HOME", "llvm-ranlib", "pige360-android-tools", "for target in aarch64-linux-android", "$target-ranlib", "tauri android init --ci --skip-targets-install", "rm -rf src-tauri/gen/android", "Falha ao gerar o projeto Android", "--profile", "--artifacts", "--verify-signature", "${app}-${profile}.$extension", "apksigner", "jarsigner -verify", "if [ \"$wants_apk\" = 'true' ]; then", "if [ \"$wants_aab\" = 'true' ]; then"):
        if required not in android:
            failures.append(f"build Android sem regeneração/contagem verificável: {required}")

    release_workflow = (ROOT / ".github/workflows/50-release.yml").read_text(encoding="utf-8")
    for required in (
        "Strawberry\\perl\\bin\\perl.exe",
        "Locale::Maketext::Simple",
        "PIGE360_STRAWBERRY_PERL",
        "GITHUB_ENV",
        "choco install strawberryperl",
        "publishable: ${{ steps.release_version.outputs.publishable }}",
        "distribution_mode: ${{ steps.release_version.outputs.distribution_mode }}",
        'gh release view "$tag" --repo "$GITHUB_REPOSITORY"',
        "needs.version.outputs.publishable == 'true'",
        "needs.version.outputs.distribution_mode == 'homologation'",
        "needs.version.outputs.distribution_mode == 'store'",
        "scripts/mobile/build-android.sh --app all --profile debug --artifacts apk --verify-signature",
        "scripts/mobile/build-ios.sh --mode local-signing",
        "iOS IPA para assinatura local",
        "needs.ios.result == 'success'",
        "vars.APPLE_DEVELOPMENT_TEAM",
        "signing_preflight",
        "SIGN_REQUIRED: 'true'",
        "scripts/mobile/sign-android.sh",
        "scripts/mobile/sign-ios.sh",
    ):
        if required not in release_workflow:
            failures.append(f"workflow desktop Windows sem preparação verificável para OpenSSL: {required}")

    if "unsigned" in release_workflow.lower():
        failures.append("workflow de release não pode publicar artefatos móveis unsigned")
    if "Assinar e verificar APKs/AABs de distribuição" not in release_workflow:
        failures.append("workflow de release Android não exige assinatura e verificação")
    if "APKs Android de depuração" not in release_workflow:
        failures.append("workflow de homologação não identifica APKs instaláveis de depuração")
    if "DISTRIBUTION_MODE" not in release_workflow:
        failures.append("workflow de release não seleciona o canal de distribuição")
    if "Assinar e verificar IPAs de distribuição" not in release_workflow:
        failures.append("workflow de release iOS não exige assinatura e verificação")

    publisher = (ROOT / "scripts/release/publish-github-release.sh").read_text(encoding="utf-8")
    for required in (
        "asset_source_id",
        "Artefato idêntico deduplicado",
        "Artefato com nome repetido preservado como",
        "RELEASE_TARGET_SHA",
        "-name '*SHA256SUMS'",
        "já contém todos os assets esperados",
    ):
        if required not in publisher:
            failures.append(f"publicador de release sem deduplicação idempotente: {required}")

    recovery_workflow = (ROOT / ".github/workflows/51-recover-release.yml").read_text(encoding="utf-8")
    recovery_kit_workflow = (ROOT / "CI_CD_KIT_LOCAL/workflows/51-recover-release.yml").read_text(encoding="utf-8")
    for required in (
        "workflow_dispatch:",
        "source_run_id:",
        "actions/download-artifact@v4",
        "merge-multiple: false",
        "RELEASE_TARGET_SHA",
        "runs/$SOURCE_RUN_ID/artifacts",
    ):
        if required not in recovery_workflow:
            failures.append(f"workflow de recuperação sem reaproveitamento verificável: {required}")
    if recovery_workflow != recovery_kit_workflow:
        failures.append("workflow de recuperação diverge do espelho CI_CD_KIT_LOCAL")

    desktop_workflow = (ROOT / ".github/workflows/31-build-desktop.yml").read_text(encoding="utf-8")
    for required in ("pull_request:", "Locale::Maketext::Simple", "PIGE360_STRAWBERRY_PERL", "libwebkit2gtk-4.1-dev"):
        if required not in desktop_workflow:
            failures.append(f"workflow manual desktop sem requisito nativo: {required}")

    android_workflow = (ROOT / ".github/workflows/32-build-android.yml").read_text(encoding="utf-8")
    for required in ("pull_request:", "android-actions/setup-android@v3", "ndk_version='27.3.13750724'", "NDK_HOME", "aarch64-linux-android", "--profile debug", "--verify-signature", "timeout-minutes: 45"):
        if required not in android_workflow:
            failures.append(f"workflow manual Android sem toolchain obrigatória: {required}")

    ios_workflow = (ROOT / ".github/workflows/33-build-ios.yml").read_text(encoding="utf-8")
    for required in ("pull_request:", "vars.APPLE_DEVELOPMENT_TEAM", "APPLE_DEVELOPMENT_TEAM", "ios_gate", "build_ios=true", "local-signing", "aarch64-apple-ios", "timeout-minutes: 60"):
        if required not in ios_workflow:
            failures.append(f"workflow iOS sem requisito de compilação verificável: {required}")
    if "CONFIGURATION_REQUIRED: defina APPLE_DEVELOPMENT_TEAM" not in ios:
        failures.append("build iOS não informa a configuração de equipe Apple ausente para o canal store")

    package_local = (ROOT / "scripts/release/package_local.py").read_text(encoding="utf-8")
    if "generate_evidence_pdf.py" not in package_local or "relatório de evidências ausente" not in package_local:
        failures.append("pacote final não gera e exige o relatório de evidências")

    result = {"status": "passed" if not failures else "failed", "failures": failures}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
