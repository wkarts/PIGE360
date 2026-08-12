#!/usr/bin/env python3
"""Gera checkpoint integral, determinístico e sem segredos do workspace PIGE360."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

FIXED_DATE = (1980, 1, 1, 0, 0, 0)
EXCLUDED_PREFIXES = (
    ".recovery/",
    ".pytest_cache/",
    ".mypy_cache/",
    ".ruff_cache/",
    ".git/",
    "release/",
    "runtime-data/",
    "runtime-secrets/",
)
EXCLUDED_PARTS = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "node_modules", ".venv", "venv", "dist", "build", "target", ".git"}
EXCLUDED_SUFFIXES = {
    ".pyc", ".pyo", ".log.tmp", ".key", ".pem", ".p12", ".pfx", ".jks", ".keystore",
}
EXCLUDED_NAMES = {".env", "id_rsa", "id_ed25519", ".DS_Store", "Thumbs.db", "CHECKPOINT_MANIFEST.json"}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def include(rel: str) -> bool:
    rel = rel.replace(os.sep, "/")
    if any(rel.startswith(prefix) for prefix in EXCLUDED_PREFIXES):
        return False
    path = PurePosixPath(rel)
    if any(part in EXCLUDED_PARTS for part in path.parts):
        return False
    if path.name in EXCLUDED_NAMES:
        return False
    if path.suffix.lower() in EXCLUDED_SUFFIXES:
        return False
    if path.name.startswith(".env.") and path.name != ".env.example":
        return False
    return True


def zip_info(name: str, executable: bool = False) -> ZipInfo:
    info = ZipInfo(name, FIXED_DATE)
    info.compress_type = ZIP_DEFLATED
    mode = 0o755 if executable else 0o644
    info.external_attr = (stat.S_IFREG | mode) << 16
    info.create_system = 3
    return info


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    root = Path(args.root).resolve()
    output = (root / args.output).resolve() if not Path(args.output).is_absolute() else Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        rel = path.relative_to(root).as_posix()
        if include(rel):
            files.append(path)
    files.sort(key=lambda item: item.relative_to(root).as_posix())

    entries: list[dict[str, object]] = []
    total_bytes = 0
    for path in files:
        data = path.read_bytes()
        rel = path.relative_to(root).as_posix()
        entries.append({"path": rel, "size": len(data), "sha256": sha256_bytes(data)})
        total_bytes += len(data)

    manifest = {
        "format": "pige360-workspace-portable-checkpoint",
        "format_version": 1,
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "workspace_version": (root / "VERSION").read_text(encoding="utf-8").strip(),
        "source_root": "local-workspace",
        "deterministic_zip_timestamp": "1980-01-01T00:00:00Z",
        "files_count": len(entries),
        "uncompressed_bytes": total_bytes,
        "exclusions": {
            "prefixes": list(EXCLUDED_PREFIXES),
            "parts": sorted(EXCLUDED_PARTS),
            "secret_suffixes": sorted(EXCLUDED_SUFFIXES),
            "secret_names": sorted(EXCLUDED_NAMES),
        },
        "files": entries,
    }
    manifest_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")

    temp = output.with_suffix(output.suffix + ".tmp")
    if temp.exists():
        temp.unlink()
    with ZipFile(temp, "w", compression=ZIP_DEFLATED, compresslevel=9, allowZip64=True) as archive:
        archive.writestr(zip_info("CHECKPOINT_MANIFEST.json"), manifest_bytes)
        for path, entry in zip(files, entries, strict=True):
            executable = bool(path.stat().st_mode & stat.S_IXUSR)
            archive.writestr(zip_info(str(entry["path"]), executable), path.read_bytes())
    temp.replace(output)

    # Validação integral do arquivo gerado.
    with ZipFile(output) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise RuntimeError("Entradas duplicadas no checkpoint")
        if any(name.startswith("/") or ".." in PurePosixPath(name).parts for name in names):
            raise RuntimeError("Caminho inseguro no checkpoint")
        packed_manifest = json.loads(archive.read("CHECKPOINT_MANIFEST.json"))
        if packed_manifest["files_count"] != len(entries):
            raise RuntimeError("Contagem do manifesto divergente")
        for entry in packed_manifest["files"]:
            data = archive.read(entry["path"])
            if len(data) != entry["size"] or sha256_bytes(data) != entry["sha256"]:
                raise RuntimeError(f"Integridade inválida: {entry['path']}")

    checksum = hashlib.sha256(output.read_bytes()).hexdigest()
    checksum_path = Path(str(output) + ".sha256")
    checksum_path.write_text(f"{checksum}  {output.name}\n", encoding="utf-8")
    external_manifest = Path(str(output) + ".manifest.json")
    external_manifest.write_bytes(manifest_bytes)
    result = {
        "output": str(output),
        "sha256": checksum,
        "bytes": output.stat().st_size,
        "files": len(entries),
        "uncompressed_bytes": total_bytes,
        "checksum_file": str(checksum_path),
        "manifest_file": str(external_manifest),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
