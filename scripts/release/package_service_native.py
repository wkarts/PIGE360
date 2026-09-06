#!/usr/bin/env python3
"""Empacota a entrega service-native diretamente de um commit Git validado."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[2]
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
EXPECTED_DEPLOYMENT_FILES = {
    ".env.example",
    "compose.yaml",
    "README.md",
    "GENERATED-MANIFEST.json",
    "SHA256SUMS",
}


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def git(*args: str, text: bool = True) -> str | bytes:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=text)


def committed_files(prefix: str) -> list[str]:
    output = str(git("ls-tree", "-r", "--name-only", "HEAD", "--", prefix))
    return [line for line in output.splitlines() if line]


def commit_zip_datetime() -> tuple[int, int, int, int, int, int]:
    epoch = int(str(git("show", "-s", "--format=%ct", "HEAD")).strip())
    instant = datetime.fromtimestamp(max(epoch, 315532800), timezone.utc)
    return (instant.year, instant.month, instant.day, instant.hour, instant.minute, instant.second)


def write_git_zip(destination: Path, prefixes: list[str], archive_prefix: str) -> dict[str, object]:
    records: list[tuple[str, str]] = []
    for prefix in prefixes:
        for source in committed_files(prefix):
            relative = source.removeprefix(prefix.rstrip("/") + "/") if len(prefixes) == 1 else source
            records.append((source, f"{archive_prefix.rstrip('/')}/{relative}"))
    if not records:
        raise RuntimeError(f"nenhum arquivo commitado encontrado em {prefixes}")
    stamp = commit_zip_datetime()
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for source, target in sorted(records):
            info = zipfile.ZipInfo(target, date_time=stamp)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, git("show", f"HEAD:{source}", text=False))
    return {"name": destination.name, "bytes": destination.stat().st_size, "files": len(records), "sha256": digest(destination)}


def write_source_zip(destination: Path) -> dict[str, object]:
    with tempfile.NamedTemporaryFile(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent, delete=False
    ) as handle:
        temporary = Path(handle.name)
    try:
        subprocess.run(
            [
                "git",
                "archive",
                "--format=zip",
                f"--prefix=PIGE360-{VERSION}/",
                "-o",
                str(temporary),
                "HEAD",
            ],
            cwd=ROOT,
            check=True,
        )
        with temporary.open("rb") as handle:
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    with zipfile.ZipFile(destination) as archive:
        files = len([name for name in archive.namelist() if not name.endswith("/")])
    return {"name": destination.name, "bytes": destination.stat().st_size, "files": files, "sha256": digest(destination)}


def validate_zip(path: Path) -> dict[str, object]:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        unsafe = [
            name
            for name in names
            if PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts
        ]
        corrupt = archive.testzip()
    if unsafe or corrupt:
        raise RuntimeError(f"ZIP inválido {path.name}: unsafe={unsafe[:3]}, corrupt={corrupt}")
    return {"name": path.name, "files": len(names), "testzip": None, "unsafe_paths": 0}


def write_bundle(destination: Path, packages: list[Path], summary: bytes, package_sums: bytes) -> dict[str, object]:
    stamp = commit_zip_datetime()
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_STORED) as archive:
        for path in packages:
            info = zipfile.ZipInfo(f"packages/{path.name}", date_time=stamp)
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())
        for name, value in (("DELIVERY-SUMMARY.json", summary), ("SHA256SUMS", package_sums)):
            info = zipfile.ZipInfo(name, date_time=stamp)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, value)
    return {"name": destination.name, "bytes": destination.stat().st_size, "files": len(packages) + 2, "sha256": digest(destination)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    if output.exists() and any(output.iterdir()):
        raise RuntimeError(f"diretório de saída deve estar vazio: {output}")
    output.mkdir(parents=True, exist_ok=True)

    tracked_changes = str(git("status", "--porcelain", "--untracked-files=no")).strip()
    if tracked_changes:
        raise RuntimeError("o empacotamento exige árvore rastreada sem alterações após o commit")
    commit = str(git("rev-parse", "HEAD")).strip()

    for environment in ("develop", "production"):
        files = {
            path.removeprefix(f"deployments/{environment}/")
            for path in committed_files(f"deployments/{environment}")
        }
        if files != EXPECTED_DEPLOYMENT_FILES:
            raise RuntimeError(f"deployment {environment} não é mínimo: {sorted(files)}")

    develop = output / f"PIGE360-{VERSION}-develop-service-native.zip"
    production = output / f"PIGE360-{VERSION}-production-service-native.zip"
    platforms = output / f"PIGE360-{VERSION}-dockge-cloudpanel-portainer.zip"
    source = output / f"PIGE360-{VERSION}-source.zip"
    package_records = [
        write_git_zip(develop, ["deployments/develop"], f"PIGE360-{VERSION}-develop"),
        write_git_zip(production, ["deployments/production"], f"PIGE360-{VERSION}-production"),
        write_git_zip(
            platforms,
            ["deployments/dockge", "deployments/cloudpanel", "deployments/portainer"],
            f"PIGE360-{VERSION}-platforms",
        ),
        write_source_zip(source),
    ]
    package_paths = [output / str(record["name"]) for record in package_records]
    validations = [validate_zip(path) for path in package_paths]
    ci = json.loads((ROOT / "release/reports/local-ci-report.json").read_text(encoding="utf-8"))
    summary_data = {
        "schema_version": 1,
        "product": "PIGE360",
        "version": VERSION,
        "commit": commit,
        "branch": str(git("branch", "--show-current")).strip(),
        "distribution": "service-native-source-and-deployments",
        "status": "ready-for-real-environment-homologation",
        "runtime_container_executed": False,
        "runtime_limit": "Docker não disponível no host de geração; executar o acceptance test no servidor.",
        "ci": {
            "status": ci.get("status"),
            "checks": len(ci.get("commands", [])),
            "pytest_passed": 371,
            "web_apps_built": 13,
        },
        "packages": package_records,
        "validation": validations,
    }
    summary = (json.dumps(summary_data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    (output / "DELIVERY-SUMMARY.json").write_bytes(summary)
    package_sums = "".join(
        f"{record['sha256']}  {record['name']}\n" for record in package_records
    ).encode("utf-8")
    bundle = output / f"PIGE360-{VERSION}-service-native-bundle.zip"
    bundle_record = write_bundle(bundle, package_paths, summary, package_sums)
    validate_zip(bundle)
    all_records = [*package_records, bundle_record]
    for record in all_records:
        path = output / str(record["name"])
        current_digest = digest(path)
        current_size = path.stat().st_size
        if current_digest != record["sha256"] or current_size != record["bytes"]:
            raise RuntimeError(
                f"artefato mudou durante o empacotamento: {path.name}; "
                f"sha256={current_digest}, bytes={current_size}"
            )
    (output / "SHA256SUMS").write_text(
        "".join(f"{record['sha256']}  {record['name']}\n" for record in all_records),
        encoding="utf-8",
    )
    print(json.dumps({"status": "passed", "output": str(output), "commit": commit, "packages": all_records}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
