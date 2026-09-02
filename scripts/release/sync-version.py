#!/usr/bin/env python3
"""Sincroniza a versão Alpha canônica do PIGE360 nos manifests públicos."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERSION_FILE = ROOT / "VERSION"
VERSION_RE = re.compile(r"\b\d+\.\d+\.\d+-alpha\.\d+\b")
PATTERNS = (
    "package.json",
    "package-lock.json",
    "README.md",
    ".env.example",
    "compose*.yaml",
    "backend/pyproject.toml",
    "backend/app/bootstrap/config.py",
    "infra/docker/**/*.Dockerfile",
    "rust/Cargo.toml",
    "apps/**/package.json",
    "apps/**/src-tauri/Cargo.toml",
    "apps/**/src-tauri/tauri.conf.json",
    "apps/**/src-tauri/gen/ios/PIGE360/Info.plist",
    "apps/**/src/app-contract.ts",
    "apps/**/src/app-contract.js",
    "apps/**/public/sw.js",
    "packages/**/package.json",
    "docs/ci-cd/ALPHA_TEST_RELEASE.md",
)


def targets() -> list[Path]:
    return sorted({path for pattern in PATTERNS for path in ROOT.glob(pattern) if path.is_file()})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("version", nargs="?", help="Versão alvo; por padrão usa VERSION")
    parser.add_argument("--check", action="store_true", help="Somente verifica se há divergências")
    args = parser.parse_args()

    target = (args.version or VERSION_FILE.read_text(encoding="utf-8").strip()).strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+-alpha\.\d+", target):
        raise SystemExit(f"Versão Alpha inválida: {target}")

    changed: list[str] = []
    mismatches: list[str] = []

    for path in targets():
        original = path.read_text(encoding="utf-8")
        found = sorted(set(VERSION_RE.findall(original)))
        if not found:
            continue
        if found == [target]:
            continue
        relative = path.relative_to(ROOT).as_posix()
        if args.check:
            mismatches.append(f"{relative}: {', '.join(found)}")
            continue
        updated = VERSION_RE.sub(target, original)
        path.write_text(updated, encoding="utf-8")
        changed.append(relative)

    if args.check:
        if mismatches:
            print("Metadados divergentes:")
            for item in mismatches:
                print(f" - {item}")
            return 1
        print(f"Metadados sincronizados em {target}.")
        return 0

    VERSION_FILE.write_text(target + "\n", encoding="utf-8")
    print(f"Versão canônica: {target}")
    print(f"Arquivos atualizados: {len(changed)}")
    for path in changed:
        print(f" - {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
