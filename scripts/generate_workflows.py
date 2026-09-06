#!/usr/bin/env python3
"""Valida os workflows canônicos e monta CI_CD_KIT_LOCAL sem reescrevê-los.

Os workflows de `.github/workflows` são a fonte de verdade. O kit local é um
espelho verificável, evitando que um gerador desatualizado restaure uploads,
deploys vazios ou comandos de placeholder.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WF = ROOT / ".github" / "workflows"
KIT = ROOT / "CI_CD_KIT_LOCAL"
REQUIRED = {
    "00-ci.yml", "03-git-flow.yml", "04-version-sync.yml", "05-cleanup-stale-release.yml",
    "05-pedagogy-attendance.yml", "10-base-images.yml", "20-application-images.yml",
    "30-build-web.yml", "31-build-desktop.yml", "32-build-android.yml", "33-build-ios.yml",
    "34-build-tenant-apps.yml", "40-security.yml", "50-release.yml", "51-recover-release.yml",
    "60-deploy-saas.yml", "61-self-hosted-bundle.yml", "70-backup-restore-test.yml",
    "80-dependency-maintenance.yml",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    actual = {p.name for p in WF.glob("*.yml")}
    missing = REQUIRED - actual
    if missing:
        raise SystemExit(f"Workflows canônicos obrigatórios ausentes: {sorted(missing)}")
    forbidden: list[str] = []
    for path in sorted(WF.glob("*.yml")):
        yaml.safe_load(path.read_text(encoding="utf-8"))
        lowered = path.read_text(encoding="utf-8").lower()
        if "deploy remoto não implementado" in lowered or "não há comando de upload" in lowered or "sleep infinity" in lowered:
            forbidden.append(path.name)
    if forbidden:
        raise SystemExit(f"Workflows com placeholder operacional: {forbidden}")

    (KIT / "workflows").mkdir(parents=True, exist_ok=True)
    (KIT / "scripts" / "release").mkdir(parents=True, exist_ok=True)
    (KIT / "scripts" / "deploy").mkdir(parents=True, exist_ok=True)
    mirrored_before = {p.name for p in (KIT / "workflows").glob("*.yml")}
    stale = mirrored_before - actual
    if stale:
        raise SystemExit(
            "O kit contém workflows sem fonte canônica; revise sem remoção automática: "
            f"{sorted(stale)}"
        )
    for path in sorted(WF.glob("*.yml")):
        shutil.copy2(path, KIT / "workflows" / path.name)
    for rel in ["scripts/release/publish-github-release.sh", "scripts/deploy/deploy-saas-ssh.sh"]:
        src = ROOT / rel
        if not src.is_file():
            raise SystemExit(f"Script obrigatório ausente: {rel}")
        dst = KIT / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    (KIT / "README.md").write_text(
        "# CI_CD_KIT_LOCAL\n\n"
        "Espelho verificável de todos os workflows canônicos. O workflow `50` "
        "tenta os 12 alvos a partir da tag imutável, mantém falhas em draft e "
        "só permite publicação parcial por decisão manual explícita. O workflow "
        "`51` redispara essa mesma matriz sem reutilizar assets antigos. Deploy "
        "remoto, assinatura e publicação em lojas continuam condicionados a "
        "flags e segredos explícitos.\n",
        encoding="utf-8",
    )
    mirrored_after = {p.name for p in (KIT / "workflows").glob("*.yml")}
    if mirrored_after != actual:
        raise SystemExit(
            "Espelho de workflows incompleto: "
            f"missing={sorted(actual - mirrored_after)}, extra={sorted(mirrored_after - actual)}"
        )
    divergent = [
        name for name in sorted(actual)
        if (WF / name).read_bytes() != (KIT / "workflows" / name).read_bytes()
    ]
    if divergent:
        raise SystemExit(f"Workflows divergentes após sincronização: {divergent}")
    files = []
    for path in sorted(KIT.rglob("*")):
        if path.is_file() and path != KIT / "manifest.json":
            files.append({"path": path.relative_to(KIT).as_posix(), "sha256": sha256(path), "bytes": path.stat().st_size})
    manifest = {"schema_version": 1, "remote_execution": False, "files": files}
    (KIT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "generated", "workflows": len(actual), "files": len(files)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
