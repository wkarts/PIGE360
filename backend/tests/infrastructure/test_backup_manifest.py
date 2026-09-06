from __future__ import annotations

import json
import tarfile
from pathlib import Path

import pytest

from scripts.backup.backup_manifest import ManifestError, create_manifest, verify_manifest


def _backup(root: Path) -> None:
    (root / "tenant-databases").mkdir(parents=True, exist_ok=True)
    (root / "objects" / "pige360-platform").mkdir(parents=True, exist_ok=True)
    (root / "objects" / "pige360-tenant-abc").mkdir(parents=True, exist_ok=True)
    (root / "platform-control.dump").write_bytes(b"control")
    tenant_file = root / "tenant-volume-record.txt"
    tenant_file.write_text("local storage", encoding="utf-8")
    with tarfile.open(root / "tenant-storage.tar.gz", "w:gz") as archive:
        archive.add(tenant_file, arcname="tenant-volume-record.txt")
    tenant_file.unlink()
    (root / "postgres-versions.txt").write_text(
        "control=pg_dump (PostgreSQL) 17.5\ntenants=pg_dump (PostgreSQL) 17.5\n",
        encoding="utf-8",
    )
    (root / "tenant-databases" / "pige360_t_abc.dump").write_bytes(b"tenant")
    (root / "objects" / "pige360-tenant-abc" / "record.txt").write_text("object", encoding="utf-8")
    (root / "tenants.tsv").write_text(
        "018f0000-0000-7000-8000-000000000001\tschool\tactive\tpige360_t_abc\tpige360_u_abc\tpige360-tenant-abc\n",
        encoding="utf-8",
    )
    (root / "buckets.txt").write_text("pige360-platform\npige360-tenant-abc\n", encoding="utf-8")


def test_manifest_round_trip_and_exact_inventory(tmp_path: Path) -> None:
    _backup(tmp_path)
    created = create_manifest(
        tmp_path,
        version="1.0.0",
        target="cloudpanel",
        image_mode="source",
        database_key_fingerprint="a" * 64,
    )

    verified = verify_manifest(tmp_path)

    assert created["tenant_count"] == 1
    assert verified["deployment_target"] == "cloudpanel"
    assert json.loads((tmp_path / "manifest.json").read_text())["consistency"] == "per-resource-online"


def test_manifest_rejects_tampering_and_added_files(tmp_path: Path) -> None:
    _backup(tmp_path)
    create_manifest(tmp_path, version="1.0.0", target="base", image_mode="registry", database_key_fingerprint="b" * 64)
    (tmp_path / "platform-control.dump").write_bytes(b"tampered")
    with pytest.raises(ManifestError, match="hash divergente"):
        verify_manifest(tmp_path)

    _backup(tmp_path)
    create_manifest(tmp_path, version="1.0.0", target="base", image_mode="registry", database_key_fingerprint="b" * 64)
    (tmp_path / "unexpected").write_text("extra", encoding="utf-8")
    with pytest.raises(ManifestError, match="conjunto de arquivos divergente"):
        verify_manifest(tmp_path)


def test_manifest_rejects_unsafe_catalog_identifiers(tmp_path: Path) -> None:
    _backup(tmp_path)
    (tmp_path / "tenants.tsv").write_text(
        "018f0000-0000-7000-8000-000000000001\tschool\tactive\tbad;drop\tpige360_u_abc\tpige360-tenant-abc\n",
        encoding="utf-8",
    )
    with pytest.raises(ManifestError, match="identificador PostgreSQL inválido"):
        create_manifest(tmp_path, version="1.0.0", target="base", image_mode="source", database_key_fingerprint="c" * 64)


def test_manifest_rejects_control_characters_in_paths(tmp_path: Path) -> None:
    _backup(tmp_path)
    (tmp_path / "objects" / "pige360-platform" / "bad\nname").write_text("unsafe", encoding="utf-8")
    with pytest.raises(ManifestError, match="caractere de controle"):
        create_manifest(
            tmp_path,
            version="1.0.0",
            target="base",
            image_mode="source",
            database_key_fingerprint="d" * 64,
        )


def test_nested_object_named_manifest_is_still_hashed(tmp_path: Path) -> None:
    _backup(tmp_path)
    nested = tmp_path / "objects/pige360-platform/manifest.json"
    nested.write_text("object payload", encoding="utf-8")
    manifest = create_manifest(
        tmp_path,
        version="1.0.0",
        target="base",
        image_mode="source",
        database_key_fingerprint="e" * 64,
    )

    assert "objects/pige360-platform/manifest.json" in {item["path"] for item in manifest["files"]}
    nested.write_text("tampered", encoding="utf-8")
    with pytest.raises(ManifestError, match="hash divergente"):
        verify_manifest(tmp_path)
