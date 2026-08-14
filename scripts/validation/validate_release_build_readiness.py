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
        text = main_rs.read_text(encoding="utf-8")
        if module_path not in text:
            failures.append(f"{app}: módulo local de comandos Tauri ausente")
        stale = [command for command in COMMANDS if f"pige360_native_bridge::{command}" in text]
        if stale:
            failures.append(f"{app}: comandos externos ainda registrados: {sorted(stale)}")
        missing = [command for command in COMMANDS if f"tauri_commands::{command}" not in text]
        if missing:
            failures.append(f"{app}: comandos locais ausentes: {sorted(missing)}")

    ios = (ROOT / "scripts/mobile/build-ios.sh").read_text(encoding="utf-8")
    if 'ios_version="${version%-alpha.*}"' not in ios or '--config "$ios_config"' not in ios:
        failures.append("build iOS não converte a versão alpha para CFBundleShortVersionString numérico")
    if 'version="$(tr -d' not in ios:
        failures.append("build iOS não deriva a versão canônica de VERSION")

    release_workflow = (ROOT / ".github/workflows/50-release.yml").read_text(encoding="utf-8")
    for required in (
        "Strawberry\\perl\\bin\\perl.exe",
        "Locale::Maketext::Simple",
        "choco install strawberryperl",
        "publishable: ${{ steps.release_version.outputs.publishable }}",
        'gh release view "$tag" --repo "$GITHUB_REPOSITORY"',
        "needs.version.outputs.publishable == 'true'",
    ):
        if required not in release_workflow:
            failures.append(f"workflow desktop Windows sem preparação verificável para OpenSSL: {required}")

    package_local = (ROOT / "scripts/release/package_local.py").read_text(encoding="utf-8")
    if "generate_evidence_pdf.py" not in package_local or "relatório de evidências ausente" not in package_local:
        failures.append("pacote final não gera e exige o relatório de evidências")

    result = {"status": "passed" if not failures else "failed", "failures": failures}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
