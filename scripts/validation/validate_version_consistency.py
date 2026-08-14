#!/usr/bin/env python3
"""Impede releases cuja versão pública diverge da versão canônica."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
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
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    valid_version = bool(re.fullmatch(r"\d+\.\d+\.\d+-alpha\.\d+", VERSION))
    mismatches: list[dict[str, object]] = []
    checked: list[str] = []
    for path in targets():
        found = sorted(set(VERSION_RE.findall(path.read_text(encoding="utf-8"))))
        if not found:
            continue
        checked.append(path.relative_to(ROOT).as_posix())
        if found != [VERSION]:
            mismatches.append({"path": path.relative_to(ROOT).as_posix(), "versions": found})

    report = {
        "schema_version": 1,
        "version": VERSION,
        "status": "passed" if valid_version and not mismatches else "failed",
        "checked_files": checked,
        "mismatches": mismatches,
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
