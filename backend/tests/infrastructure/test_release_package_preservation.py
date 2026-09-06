from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
PACKAGER = ROOT / "scripts/release/package_local.py"


def load_packager():
    spec = importlib.util.spec_from_file_location("pige360_package_local", PACKAGER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_source_inventory_preserves_vue_js_main_js_and_origin_manifest() -> None:
    module = load_packager()
    names = {name for name, _ in module.source_entries()}

    vue_sources = sorted(name for name in names if name.startswith("apps/") and name.endswith(".vue"))
    vue_js = sorted(name for name in names if name.startswith("apps/") and name.endswith(".vue.js"))
    main_js = sorted(
        name
        for name in names
        if name.startswith("apps/") and name.endswith("/src/main.js")
    )

    assert len(vue_js) >= 50
    assert {f"{name}.js" for name in vue_sources} == set(vue_js)
    assert len(main_js) == 13
    # O manifesto alpha permanece no repositório apenas como evidência histórica;
    # bundles atuais não podem apresentá-lo como manifesto da entrega.
    assert "CHECKPOINT_MANIFEST.json" not in names
    assert "release/version-consistency.json" in names
    assert not any("node_modules" in Path(name).parts for name in names)
    assert not any("dist" in Path(name).parts for name in names)
    assert not any(".continua-ai" in Path(name).parts for name in names)


def test_zip_uses_source_mtime_and_preservation_gate(tmp_path: Path) -> None:
    module = load_packager()
    vue_js = tmp_path / "App.vue.js"
    main_js = tmp_path / "main.js"
    vue_js.write_text("export default {};\n", encoding="utf-8")
    main_js.write_text("export {};\n", encoding="utf-8")
    expected = datetime(2026, 9, 4, 12, 34, 56, tzinfo=timezone.utc)
    timestamp = expected.timestamp()
    os.utime(vue_js, (timestamp, timestamp))
    os.utime(main_js, (timestamp, timestamp))
    entries = [
        ("apps/example/src/App.vue.js", vue_js),
        ("apps/example/src/main.js", main_js),
    ]
    archive = tmp_path / "source.zip"

    result = module.make_zip(archive, entries)
    preservation = module.validate_source_preservation(archive, entries)

    assert result["timestamp_policy"] == "source_mtime_utc"
    assert preservation["vue_js_preserved"] == 1
    assert preservation["main_js_preserved"] == 1
    with zipfile.ZipFile(archive) as packaged:
        assert packaged.getinfo("apps/example/src/App.vue.js").date_time == time.gmtime(timestamp)[:6]


def test_zip_is_streamed_and_atomically_preserves_previous_file_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = load_packager()
    source = tmp_path / "large-source.bin"
    source.write_bytes(b"source-data" * 1024)
    archive = tmp_path / "source.zip"
    first = module.make_zip(archive, [("source.bin", source)])
    original = archive.read_bytes()

    monkeypatch.setattr(
        Path,
        "read_bytes",
        lambda _self: (_ for _ in ()).throw(AssertionError("read_bytes recusado")),
    )
    assert module.assert_zip_snapshot(archive, first, stage="teste")["testzip"] is None

    def interrupted_copy(*_args, **_kwargs):
        raise OSError("simulated interrupted write")

    monkeypatch.setattr(module.shutil, "copyfileobj", interrupted_copy)
    with pytest.raises(OSError, match="interrupted write"):
        module.make_zip(archive, [("source.bin", source)])

    with archive.open("rb") as stream:
        assert stream.read() == original
    assert module.assert_zip_snapshot(archive, first, stage="após falha")["testzip"] is None
    assert not list(tmp_path.glob(f".{archive.name}.*.tmp"))
    assert not list(
        tmp_path.parent.glob(f".{tmp_path.name}.{archive.name}.staging-*")
    )


def test_zip_snapshot_detects_post_build_mutation(tmp_path: Path) -> None:
    module = load_packager()
    source = tmp_path / "source.txt"
    source.write_text("stable\n", encoding="utf-8")
    archive = tmp_path / "source.zip"
    snapshot = module.make_zip(archive, [("source.txt", source)])

    with archive.open("ab") as stream:
        stream.write(b"unexpected trailing bytes")

    with pytest.raises(RuntimeError, match="ZIP imutável mudou"):
        module.assert_zip_snapshot(archive, snapshot, stage="regressão")


def test_self_hosted_only_runs_without_prebuilt_release_evidence(tmp_path: Path) -> None:
    script = tmp_path / "scripts/release/package_local.py"
    script.parent.mkdir(parents=True)
    shutil.copy2(PACKAGER, script)
    (tmp_path / "VERSION").write_text("1.2.3\n", encoding="utf-8")
    (tmp_path / "package.json").write_text('{"name":"pige360-test"}\n', encoding="utf-8")
    vue_js = tmp_path / "apps/example/src/App.vue.js"
    vue_js.parent.mkdir(parents=True)
    vue_js.write_text("export default {};\n", encoding="utf-8")
    (vue_js.parent / "main.js").write_text("export {};\n", encoding="utf-8")
    output = tmp_path / "release/output"

    process = subprocess.run(
        [sys.executable, str(script), "--self-hosted-only", "--output-dir", str(output)],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )

    assert process.returncode == 0, process.stdout + process.stderr
    summary = json.loads((output / "DELIVERY-SUMMARY.json").read_text(encoding="utf-8"))
    assert summary["status"] == "passed"
    assert summary["timestamp_policy"] == "source_mtime_utc"
    with zipfile.ZipFile(output / "PIGE360-1.2.3-self-hosted.zip") as packaged:
        names = set(packaged.namelist())
        assert "apps/example/src/App.vue.js" in names
        assert "apps/example/src/main.js" in names
        assert packaged.testzip() is None


def test_delivery_cleanup_requires_safe_target_and_ownership_marker(tmp_path: Path) -> None:
    module = load_packager()
    project = tmp_path / "project"
    project.mkdir()

    with pytest.raises(RuntimeError, match="perigoso"):
        module.prepare_delivery(project, root=project)

    protected = project / "docs"
    protected.mkdir()
    with pytest.raises(RuntimeError, match="release/output"):
        module.prepare_delivery(protected, root=project)

    unmanaged = tmp_path / "existing"
    unmanaged.mkdir()
    (unmanaged / "keep.txt").write_text("preserve", encoding="utf-8")
    with pytest.raises(RuntimeError, match="sem marcador"):
        module.prepare_delivery(unmanaged, root=project)
    assert (unmanaged / "keep.txt").read_text(encoding="utf-8") == "preserve"

    managed = module.prepare_delivery(tmp_path / "delivery", root=project)
    (managed / "old.txt").write_text("old", encoding="utf-8")
    recreated = module.prepare_delivery(managed, root=project)
    assert recreated == managed
    assert not (managed / "old.txt").exists()
    assert (managed / module.DELIVERY_MARKER).is_file()
    marker_data = json.loads((managed / module.DELIVERY_MARKER).read_text(encoding="utf-8"))
    assert "path" not in marker_data
    assert marker_data["directory_identity"] == module.delivery_identity(managed)

    copied_marker_target = tmp_path / "copied-marker"
    copied_marker_target.mkdir()
    shutil.copy2(managed / module.DELIVERY_MARKER, copied_marker_target / module.DELIVERY_MARKER)
    (copied_marker_target / "keep.txt").write_text("preserve", encoding="utf-8")
    with pytest.raises(RuntimeError, match="sem marcador"):
        module.prepare_delivery(copied_marker_target, root=project)
    assert (copied_marker_target / "keep.txt").is_file()

    symlink_marker_target = tmp_path / "symlink-marker"
    symlink_marker_target.mkdir()
    (symlink_marker_target / "keep.txt").write_text("preserve", encoding="utf-8")
    (symlink_marker_target / module.DELIVERY_MARKER).symlink_to(
        managed / module.DELIVERY_MARKER
    )
    with pytest.raises(RuntimeError, match="sem marcador"):
        module.prepare_delivery(symlink_marker_target, root=project)
    assert (symlink_marker_target / "keep.txt").is_file()


def test_delivery_lock_refuses_a_second_writer(tmp_path: Path) -> None:
    module = load_packager()
    delivery = tmp_path / "delivery"
    first = module.acquire_delivery_lock(delivery)
    try:
        with pytest.raises(RuntimeError, match="outro empacotamento"):
            module.acquire_delivery_lock(delivery)
    finally:
        first.close()

    second = module.acquire_delivery_lock(delivery)
    second.close()


def test_checksums_refuse_temporary_or_hidden_delivery_residue(tmp_path: Path) -> None:
    module = load_packager()
    (tmp_path / "package.zip").write_bytes(b"package")
    (tmp_path / ".package.zip.interrupted.tmp").write_bytes(b"partial")

    with pytest.raises(RuntimeError, match="resíduos"):
        module.write_checksums(tmp_path)

    assert not (tmp_path / "SHA256SUMS").exists()


def test_source_manifest_detects_changes_before_or_after_zip(tmp_path: Path) -> None:
    module = load_packager()
    source = tmp_path / "source.js"
    source.write_text("export const value = 1;\n", encoding="utf-8")
    entries = [("apps/example/src/source.js", source)]
    tree = {
        "files_count": 1,
        "tree_sha256": "fixture-tree",
        "files": [{"path": entries[0][0], "sha256": module.sha(source)}],
    }
    archive = tmp_path / "source.zip"
    module.make_zip(archive, entries)

    assert module.validate_source_manifest(archive, tree, entries)["status"] == "passed"
    source.write_text("export const value = 2;\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="manifesto imutável"):
        module.validate_source_manifest(archive, tree, entries)


def test_external_evidence_is_explicit_allowlisted_and_strictly_scanned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = load_packager()
    source = tmp_path / "incoming"
    source.mkdir()
    (source / "result.json").write_text('{"status":"passed"}\n', encoding="utf-8")
    destination = tmp_path / "staged"
    monkeypatch.setenv("PIGE360_EVIDENCE_DIR", str(source))

    result = module.import_external_evidence(destination)
    assert result["status"] == "passed"
    assert (destination / "result.json").is_file()

    (source / "secrets.log").write_text(
        "password=12345678901234567890\n", encoding="utf-8"
    )
    with pytest.raises(RuntimeError, match="varredura de segredos"):
        module.import_external_evidence(destination)
    assert (destination / "result.json").is_file()


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _valid_release_evidence(root: Path, module) -> None:
    version = "1.2.3"
    log = root / "release/reports/logs/gate.log"
    log.parent.mkdir(parents=True)
    log.write_text("passed\n", encoding="utf-8")
    commands = [
        {
            "name": name,
            "status": "passed",
            "log": "release/reports/logs/gate.log",
            "finished_at": "2030-01-01T00:00:00+00:00",
        }
        for name in sorted(module.REQUIRED_CI_COMMANDS)
    ]
    _write_json(
        root / "release/reports/local-ci-report.json",
        {"status": "passed", "version": version, "commands": commands},
    )
    _write_json(
        root / "release/reports/test-report.json",
        {
            "status": "passed",
            "version": version,
            "pytest_passed": 1,
            "failed_checks": [],
        },
    )
    _write_json(
        root / "release/reports/build-report.json",
        {
            "status": "passed",
            "version": version,
            "builds": {
                "backend": {"status": "passed"},
                "web_pwa_source": {
                    "status": "passed",
                    "production_bundle_executed": True,
                },
            },
        },
    )
    _write_json(
        root / "release/version-consistency.json",
        {
            "status": "passed",
            "version": version,
            "stable_semver": True,
            "product_prereleases": [],
        },
    )
    _write_json(
        root / "release/project-validation.json",
        {"status": "passed", "version": version},
    )
    _write_json(
        root / "release/secret-scan-report.json",
        {
            "status": "passed",
            "version": version,
            "findings": [],
            "scanned_files": 1,
        },
    )
    _write_json(
        root / "docs/api/OPENAPI_REPORT.json",
        {"version": version, "duplicate_operation_ids": []},
    )
    _write_json(
        root / "docs/operations/BEFORE_AFTER_REPORT.json",
        {"summary": {"preservation_status": "passed", "removed": 0}},
    )
    _write_json(
        root / f"release/PIGE360-{version}-sbom.cdx.json",
        {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "metadata": {"component": {"version": version}},
            "properties": [
                {"name": "pige360:cargo-resolution", "value": "cargo-lock"},
                {"name": "pige360:cargo-lockfiles", "value": "14"},
                {"name": "pige360:cargo-lockfiles-expected", "value": "14"},
            ],
        },
    )
    _write_json(
        root / "release/artifacts/backup-restore/report.json",
        {"status": "passed"},
    )
    oci = root / f"release/artifacts/oci/PIGE360-{version}-images-oci.tar"
    oci.parent.mkdir(parents=True)
    oci.write_bytes(b"oci-fixture")
    _write_json(
        root / f"release/artifacts/oci/PIGE360-{version}-images-digests.json",
        {
            "version": version,
            "bundle": {"sha256": module.sha(oci)},
        },
    )


def test_release_evidence_gate_is_fail_closed_for_status_version_and_freshness(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = load_packager()
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module, "VERSION", "1.2.3")
    _valid_release_evidence(tmp_path, module)
    source = tmp_path / "apps/example/src/main.js"
    source.parent.mkdir(parents=True)
    source.write_text("export {};\n", encoding="utf-8")
    monkeypatch.setattr(module, "source_entries", lambda **_kwargs: [("apps/example/src/main.js", source)])
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess([], 0, "verified", ""),
    )

    assert module.validate_release_evidence()["status"] == "passed"

    sbom_path = tmp_path / "release/PIGE360-1.2.3-sbom.cdx.json"
    sbom = json.loads(sbom_path.read_text(encoding="utf-8"))
    sbom["properties"][0]["value"] = "manifest-only"
    sbom["properties"][1]["value"] = "0"
    _write_json(sbom_path, sbom)
    with pytest.raises(RuntimeError, match="SBOM Rust"):
        module.validate_release_evidence()
    candidate = module.validate_release_evidence(source_candidate=True)
    assert candidate["status"] == "partial"
    assert candidate["distribution_channel"] == "source-candidate"
    assert candidate["publishable_release"] is False
    assert candidate["native_builds"]["status"] == "not-built"
    assert candidate["native_builds"]["cargo_lockfiles"] == 0

    sbom["properties"][0]["value"] = "cargo-lock"
    sbom["properties"][1]["value"] = "1"
    _write_json(sbom_path, sbom)
    with pytest.raises(RuntimeError, match="SBOM Rust"):
        module.validate_release_evidence(source_candidate=True)
    sbom["properties"][0]["value"] = "cargo-lock"
    sbom["properties"][1]["value"] = "14"
    _write_json(sbom_path, sbom)

    project = tmp_path / "release/project-validation.json"
    _write_json(project, {"status": "passed", "version": "9.9.9"})
    with pytest.raises(RuntimeError, match="validacao do projeto|validação do projeto"):
        module.validate_release_evidence()
    _write_json(project, {"status": "passed", "version": "1.2.3"})

    ci_path = tmp_path / "release/reports/local-ci-report.json"
    ci = json.loads(ci_path.read_text(encoding="utf-8"))
    ci["commands"][0]["status"] = "failed"
    _write_json(ci_path, ci)
    with pytest.raises(RuntimeError, match="comandos nao aprovados|comandos não aprovados"):
        module.validate_release_evidence()
    ci["commands"][0]["status"] = "passed"
    _write_json(ci_path, ci)

    future = datetime(2031, 1, 1, tzinfo=timezone.utc).timestamp()
    os.utime(source, (future, future))
    with pytest.raises(RuntimeError, match="anterior ao fonte atual"):
        module.validate_release_evidence()


def test_source_candidate_names_and_manifests_cannot_be_mistaken_for_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = load_packager()
    monkeypatch.setattr(module, "VERSION", "1.2.3")
    assert module.distribution_stem(False) == "PIGE360-1.2.3"
    assert module.distribution_stem(True) == "PIGE360-1.2.3-source-candidate"
    document = tmp_path / "candidate.json"
    _write_json(document, {"schema_version": 1})
    gate = {
        "native_builds": {
            "status": "not-built",
            "cargo_lockfiles": 0,
            "cargo_lockfiles_expected": 14,
            "reason": "Rust/Cargo indisponível neste host; nenhum binário nativo foi construído.",
        }
    }
    module.annotate_source_candidate(document, gate)
    annotated = json.loads(document.read_text(encoding="utf-8"))
    assert annotated["distribution"]["status"] == "partial"
    assert annotated["distribution"]["publishable_release"] is False
    assert annotated["distribution"]["native_builds"]["status"] == "not-built"
