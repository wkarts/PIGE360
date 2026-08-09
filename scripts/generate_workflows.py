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
EXPECTED = {
    "00-ci.yml", "05-pedagogy-attendance.yml", "10-base-images.yml", "20-application-images.yml",
    "30-build-web.yml", "31-build-desktop.yml", "32-build-android.yml", "33-build-ios.yml",
    "34-build-tenant-apps.yml", "40-security.yml", "50-release.yml", "60-deploy-saas.yml",
    "61-self-hosted-bundle.yml", "70-backup-restore-test.yml", "80-dependency-maintenance.yml",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    actual = {p.name for p in WF.glob("*.yml")}
    if actual != EXPECTED:
        raise SystemExit(f"Conjunto de workflows divergente. missing={sorted(EXPECTED-actual)} extra={sorted(actual-EXPECTED)}")
    forbidden: list[str] = []
    for path in sorted(WF.glob("*.yml")):
        yaml.safe_load(path.read_text(encoding="utf-8"))
        lowered = path.read_text(encoding="utf-8").lower()
        if "deploy remoto não implementado" in lowered or "não há comando de upload" in lowered or "sleep infinity" in lowered:
            forbidden.append(path.name)
    if forbidden:
        raise SystemExit(f"Workflows com placeholder operacional: {forbidden}")

    if KIT.exists():
        shutil.rmtree(KIT)
    (KIT / "workflows").mkdir(parents=True)
    (KIT / "scripts" / "release").mkdir(parents=True)
    (KIT / "scripts" / "deploy").mkdir(parents=True)
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
        "Espelho verificável dos workflows canônicos. Publicação e deploy remoto continuam desabilitados por padrão e exigem flags + segredos explícitos.\n",
        encoding="utf-8",
    )
    files = []
    for path in sorted(KIT.rglob("*")):
        if path.is_file():
            files.append({"path": path.relative_to(KIT).as_posix(), "sha256": sha256(path), "bytes": path.stat().st_size})
    manifest = {"schema_version": 1, "remote_execution": False, "files": files}
    (KIT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "generated", "workflows": len(EXPECTED), "files": len(files)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
