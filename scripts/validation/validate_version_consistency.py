#!/usr/bin/env python3
"""Valida que o PIGE360 usa somente SemVer estável X.Y.Z e não contém prereleases públicas."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
STABLE_RE = re.compile(r"\d+\.\d+\.\d+")
PRERELEASE_RE = re.compile(r"\b\d+\.\d+\.\d+-(?:alpha|beta|rc|pre|preview|dev|snapshot)(?:[.-][0-9A-Za-z.-]+)?\b", re.IGNORECASE)
PATTERNS = (
    "VERSION",
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
    "docs/ci-cd/*.md",
)


def targets() -> list[Path]:
    return sorted({path for pattern in PATTERNS for path in ROOT.glob(pattern) if path.is_file()})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    valid_version = bool(STABLE_RE.fullmatch(VERSION))
    prereleases: list[dict[str, object]] = []
    checked: list[str] = []
    for path in targets():
        text = path.read_text(encoding="utf-8")
        found = sorted(set(PRERELEASE_RE.findall(text)))
        relative = path.relative_to(ROOT).as_posix()
        checked.append(relative)
        matches = sorted(set(match.group(0) for match in PRERELEASE_RE.finditer(text)))
        if matches:
            prereleases.append({"path": relative, "versions": matches})

    report = {
        "schema_version": 2,
        "version": VERSION,
        "stable_semver": valid_version,
        "status": "passed" if valid_version and not prereleases else "failed",
        "checked_files": checked,
        "prereleases": prereleases,
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
