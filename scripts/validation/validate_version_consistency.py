#!/usr/bin/env python3
"""Valida SemVer e cada campo de versão mantido pelo release.

O modo padrão continua restrito à versão estável. ``--allow-prerelease`` é um
gate explícito reservado à reconstrução técnica de uma tag prerelease já
imutável; ele não altera a criação automática de versões oficiais.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
STABLE_RE = re.compile(r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)")
SEMVER_RE = re.compile(
    r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)"
    r"(?:-(?:0|[1-9]\d*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9]\d*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*))*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
)
PRODUCT_PRERELEASE_RE = re.compile(
    r"\b(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)"
    r"-alpha(?:[.-][0-9A-Za-z.-]+)?\b",
    re.IGNORECASE,
)
REQUIRED_DOCKERFILES = {
    "infra/docker/Dockerfile.api",
    "infra/docker/Dockerfile.migrations",
    "infra/docker/Dockerfile.reporting",
    "infra/docker/Dockerfile.web",
    "infra/docker/Dockerfile.worker",
    "infra/docker/base/Dockerfile.node",
    "infra/docker/base/Dockerfile.python",
    "infra/docker/base/Dockerfile.runtime",
    "infra/docker/base/Dockerfile.rust-tauri",
    "infra/docker/build-farm/Dockerfile.linux",
}


def _load_sync_module() -> ModuleType:
    path = ROOT / "scripts/release/sync-version.py"
    spec = importlib.util.spec_from_file_location("pige360_sync_version", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"não foi possível carregar {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def is_valid_version(version: str, *, allow_prerelease: bool = False) -> bool:
    if STABLE_RE.fullmatch(version):
        return True
    return allow_prerelease and bool(SEMVER_RE.fullmatch(version))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--allow-prerelease",
        action="store_true",
        help="Aceita SemVer prerelease somente para validar uma tag técnica já existente",
    )
    args = parser.parse_args()

    stable_version = bool(STABLE_RE.fullmatch(VERSION))
    valid_version = is_valid_version(VERSION, allow_prerelease=args.allow_prerelease)
    sync = _load_sync_module()
    paths = sync.metadata_paths()
    checked = [path.relative_to(ROOT).as_posix() for path in paths]

    metadata_mismatches: list[dict[str, str]] = []
    prereleases: list[dict[str, object]] = []
    for path in paths:
        text = path.read_text(encoding="utf-8")
        relative = path.relative_to(ROOT).as_posix()
        if sync.transform(path, text, VERSION) != text:
            metadata_mismatches.append({"path": relative, "expected": VERSION})

        # package-lock contém metadados de terceiros. Os campos do projeto nele
        # já foram validados estruturalmente acima; não trate prereleases externos
        # como versões do PIGE360.
        if relative == "package-lock.json":
            continue
        matches = [] if args.allow_prerelease else sorted(
            set(match.group(0) for match in PRODUCT_PRERELEASE_RE.finditer(text))
        )
        if matches:
            prereleases.append({"path": relative, "versions": matches})

    dockerfiles = {
        path.relative_to(ROOT).as_posix()
        for path in ROOT.glob("infra/docker/**/Dockerfile*")
        if path.is_file()
    }
    inventory_errors: list[dict[str, object]] = []
    missing_dockerfiles = sorted(REQUIRED_DOCKERFILES - dockerfiles)
    if missing_dockerfiles:
        inventory_errors.append({"kind": "missing_dockerfiles", "paths": missing_dockerfiles})
    unchecked_dockerfiles = sorted(dockerfiles - set(checked))
    if unchecked_dockerfiles:
        inventory_errors.append({"kind": "unchecked_dockerfiles", "paths": unchecked_dockerfiles})
    dockerfiles_without_version_arg = sorted(
        relative
        for relative in dockerfiles
        if not re.search(
            r"^ARG VERSION=\S+$",
            (ROOT / relative).read_text(encoding="utf-8"),
            flags=re.MULTILINE,
        )
    )
    if dockerfiles_without_version_arg:
        inventory_errors.append(
            {"kind": "dockerfiles_without_version_arg", "paths": dockerfiles_without_version_arg}
        )

    failures: list[dict[str, object]] = [*prereleases, *metadata_mismatches, *inventory_errors]
    report = {
        "schema_version": 3,
        "version": VERSION,
        "stable_semver": stable_version,
        "valid_semver": valid_version,
        "allow_prerelease": args.allow_prerelease,
        "status": "passed" if valid_version and not failures else "failed",
        "checked_files": checked,
        "checked_dockerfiles": sorted(dockerfiles),
        "product_prereleases": prereleases,
        "metadata_mismatches": metadata_mismatches,
        "inventory_errors": inventory_errors,
        # Alias preservado para consumidores internos do relatório v2.
        "mismatches": failures,
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
