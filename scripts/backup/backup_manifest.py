#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
import tarfile
from uuid import UUID
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any


SCHEMA_VERSION = 1
TENANT_COLUMNS = ("tenant_id", "code", "status", "database_name", "database_user", "bucket_name")
PG_IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")
BUCKET_NAME = re.compile(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")
TENANT_CODE = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")
OPERATIONAL_STATUSES = frozenset({"active", "degraded", "suspended"})
DEPLOYMENT_TARGETS = frozenset({"base", "cloudpanel", "edge", "dockge", "portainer"})
IMAGE_MODES = frozenset({"source", "registry"})
STABLE_SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


class ManifestError(ValueError):
    pass


def _safe_relative(value: str) -> PurePosixPath:
    if "\\" in value or any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ManifestError(f"caminho contém caractere de controle ou separador incompatível: {value!r}")
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts or "." in path.parts:
        raise ManifestError(f"caminho inseguro no manifesto: {value!r}")
    return path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_catalog(path: Path) -> list[dict[str, str]]:
    if not path.is_file() or path.is_symlink():
        raise ManifestError("catálogo tenants.tsv ausente ou inseguro")
    rows: list[dict[str, str]] = []
    seen_tenant_ids: set[str] = set()
    seen_codes: set[str] = set()
    seen_databases: set[str] = set()
    seen_buckets: set[str] = set()
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle, delimiter="\t", quoting=csv.QUOTE_NONE)
        for line_number, values in enumerate(reader, 1):
            if not values or all(not item for item in values):
                continue
            if len(values) != len(TENANT_COLUMNS):
                raise ManifestError(f"tenants.tsv linha {line_number}: esperadas 6 colunas")
            row = dict(zip(TENANT_COLUMNS, values, strict=True))
            database = row["database_name"]
            user = row["database_user"]
            bucket = row["bucket_name"]
            try:
                UUID(row["tenant_id"])
            except ValueError as exc:
                raise ManifestError(f"tenants.tsv linha {line_number}: UUID de tenant inválido") from exc
            if not TENANT_CODE.fullmatch(row["code"]):
                raise ManifestError(f"tenants.tsv linha {line_number}: código de tenant inválido")
            if row["status"] not in OPERATIONAL_STATUSES:
                raise ManifestError(f"tenants.tsv linha {line_number}: status não operacional")
            if not PG_IDENTIFIER.fullmatch(database) or not PG_IDENTIFIER.fullmatch(user):
                raise ManifestError(f"tenants.tsv linha {line_number}: identificador PostgreSQL inválido")
            if not BUCKET_NAME.fullmatch(bucket):
                raise ManifestError(f"tenants.tsv linha {line_number}: bucket inválido")
            if (
                row["tenant_id"] in seen_tenant_ids
                or row["code"] in seen_codes
                or database in seen_databases
                or bucket in seen_buckets
            ):
                raise ManifestError(f"tenants.tsv linha {line_number}: recurso duplicado")
            seen_tenant_ids.add(row["tenant_id"])
            seen_codes.add(row["code"])
            seen_databases.add(database)
            seen_buckets.add(bucket)
            rows.append(row)
    return rows


def validate_catalog(root: Path) -> list[dict[str, str]]:
    rows = read_catalog(root / "tenants.tsv")
    for row in rows:
        dump = root / "tenant-databases" / f"{row['database_name']}.dump"
        if not dump.is_file() or dump.is_symlink():
            raise ManifestError(f"dump de tenant ausente: {dump.name}")
        bucket_dir = root / "objects" / row["bucket_name"]
        if not bucket_dir.is_dir() or bucket_dir.is_symlink():
            raise ManifestError(f"snapshot de bucket ausente: {row['bucket_name']}")
    platform_bucket = root / "objects" / "pige360-platform"
    if not platform_bucket.is_dir() or platform_bucket.is_symlink():
        raise ManifestError("snapshot do bucket pige360-platform ausente")
    return rows


def validate_tenant_storage_archive(path: Path) -> None:
    if not path.is_file() or path.is_symlink():
        raise ManifestError("tenant-storage.tar.gz ausente ou inseguro")
    try:
        with tarfile.open(path, mode="r:gz") as archive:
            for member in archive.getmembers():
                _safe_relative(member.name)
                if member.issym() or member.islnk() or member.isdev():
                    raise ManifestError(f"entrada insegura no tenant storage: {member.name}")
    except tarfile.TarError as exc:
        raise ManifestError("tenant-storage.tar.gz inválido") from exc


def _data_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ManifestError(f"links simbólicos não são aceitos no backup: {path.relative_to(root)}")
        relative = path.relative_to(root).as_posix()
        if path.is_file() and relative not in {"manifest.json", "SHA256SUMS"}:
            _safe_relative(relative)
            files.append(path)
    return files


def _postgres_major(path: Path) -> int:
    matches = re.findall(r"PostgreSQL\)\s+(\d+)(?:\.|\s|$)", path.read_text(encoding="utf-8"))
    if not matches or len(set(matches)) != 1:
        raise ManifestError("versões Control/Tenants do PostgreSQL ausentes ou incompatíveis")
    return int(matches[0])


def create_manifest(
    root: Path,
    *,
    version: str,
    target: str,
    image_mode: str,
    database_key_fingerprint: str,
) -> dict[str, Any]:
    if not (root / "platform-control.dump").is_file():
        raise ManifestError("platform-control.dump ausente")
    validate_tenant_storage_archive(root / "tenant-storage.tar.gz")
    versions_path = root / "postgres-versions.txt"
    if not versions_path.is_file() or "PostgreSQL" not in versions_path.read_text(encoding="utf-8"):
        raise ManifestError("versões do PostgreSQL ausentes ou inválidas")
    postgres_major = _postgres_major(versions_path)
    tenants = validate_catalog(root)
    validate_tenant_storage_archive(root / "tenant-storage.tar.gz")
    if not STABLE_SEMVER.fullmatch(version):
        raise ManifestError("versão do backup não segue SemVer estável")
    if target not in DEPLOYMENT_TARGETS or image_mode not in IMAGE_MODES:
        raise ManifestError("target ou modo de imagem inválido")
    if not re.fullmatch(r"[0-9a-f]{64}", database_key_fingerprint):
        raise ManifestError("fingerprint da chave de banco inválido")
    files = [
        {
            "path": path.relative_to(root).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": _sha256(path),
        }
        for path in _data_files(root)
    ]
    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "product": "PIGE360",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "version": version,
        "deployment_target": target,
        "image_mode": image_mode,
        "database_secret_key_sha256": database_key_fingerprint,
        "postgres_major": postgres_major,
        "consistency": "per-resource-online",
        "tenant_count": len(tenants),
        "files": files,
    }
    manifest_path = root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    checksum_rows = [(item["sha256"], item["path"]) for item in files]
    checksum_rows.append((_sha256(manifest_path), "manifest.json"))
    (root / "SHA256SUMS").write_text(
        "".join(f"{digest}  {path}\n" for digest, path in sorted(checksum_rows, key=lambda item: item[1])),
        encoding="utf-8",
    )
    return manifest


def verify_manifest(root: Path) -> dict[str, Any]:
    manifest_path = root / "manifest.json"
    checksum_path = root / "SHA256SUMS"
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise ManifestError("manifest.json ausente ou inseguro")
    if not checksum_path.is_file() or checksum_path.is_symlink():
        raise ManifestError("SHA256SUMS ausente ou inseguro")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != SCHEMA_VERSION or manifest.get("product") != "PIGE360":
        raise ManifestError("schema/produto do manifesto incompatível")
    if not STABLE_SEMVER.fullmatch(str(manifest.get("version", ""))):
        raise ManifestError("versão do manifesto inválida")
    if manifest.get("deployment_target") not in DEPLOYMENT_TARGETS or manifest.get("image_mode") not in IMAGE_MODES:
        raise ManifestError("target ou modo de imagem incompatível")
    versions_path = root / "postgres-versions.txt"
    if manifest.get("postgres_major") != _postgres_major(versions_path):
        raise ManifestError("versão PostgreSQL do manifesto diverge do inventário")

    expected: dict[str, str] = {}
    for item in manifest.get("files", []):
        relative = _safe_relative(str(item.get("path", ""))).as_posix()
        digest = str(item.get("sha256", ""))
        size = item.get("bytes")
        if relative in expected or not re.fullmatch(r"[0-9a-f]{64}", digest) or not isinstance(size, int) or size < 0:
            raise ManifestError("entrada duplicada ou hash inválido no manifesto")
        expected[relative] = digest

    actual_files = {
        path.relative_to(root).as_posix()
        for path in _data_files(root)
    }
    if actual_files != set(expected):
        missing = sorted(set(expected) - actual_files)
        extra = sorted(actual_files - set(expected))
        raise ManifestError(f"conjunto de arquivos divergente; ausentes={missing}, extras={extra}")
    for item in manifest.get("files", []):
        relative = str(item["path"])
        digest = str(item["sha256"])
        path = root.joinpath(*PurePosixPath(relative).parts)
        if path.is_symlink() or path.stat().st_size != item.get("bytes") or _sha256(path) != digest:
            raise ManifestError(f"hash divergente: {relative}")

    checksum_expected = {**expected, "manifest.json": _sha256(manifest_path)}
    checksum_actual: dict[str, str] = {}
    for line in checksum_path.read_text(encoding="utf-8").splitlines():
        digest, separator, relative = line.partition("  ")
        if not separator:
            raise ManifestError("linha inválida em SHA256SUMS")
        relative = _safe_relative(relative).as_posix()
        if relative in checksum_actual:
            raise ManifestError("entrada duplicada em SHA256SUMS")
        checksum_actual[relative] = digest
    if checksum_actual != checksum_expected:
        raise ManifestError("SHA256SUMS não corresponde ao manifesto")
    tenants = validate_catalog(root)
    if manifest.get("tenant_count") != len(tenants):
        raise ManifestError("tenant_count não corresponde ao catálogo")
    if not re.fullmatch(r"[0-9a-f]{64}", str(manifest.get("database_secret_key_sha256", ""))):
        raise ManifestError("fingerprint da chave de banco ausente ou inválido")
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cria e verifica manifestos de backup PIGE360.")
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate-catalog")
    validate.add_argument("root", type=Path)
    create = sub.add_parser("create")
    create.add_argument("root", type=Path)
    create.add_argument("--version", required=True)
    create.add_argument("--target", required=True)
    create.add_argument("--image-mode", required=True)
    create.add_argument("--database-key-fingerprint", required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("root", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "validate-catalog":
            rows = read_catalog(args.root / "tenants.tsv")
            print(json.dumps({"tenant_count": len(rows)}, sort_keys=True))
        elif args.command == "create":
            print(json.dumps(create_manifest(
                args.root,
                version=args.version,
                target=args.target,
                image_mode=args.image_mode,
                database_key_fingerprint=args.database_key_fingerprint,
            ), sort_keys=True))
        else:
            print(json.dumps(verify_manifest(args.root), sort_keys=True))
    except (ManifestError, json.JSONDecodeError, OSError) as exc:
        print(f"Backup inválido: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
