#!/usr/bin/env python3
"""Coleta evidencias de release sem transformar metadados em execucao real.

Este modulo e deliberadamente independente de Git e de caminhos do workspace do
autor. Os geradores de manifesto, proveniencia e PDF usam as mesmas fontes para
evitar numeros divergentes entre os artefatos finais.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


def project_root(value: str | Path | None = None) -> Path:
    configured = value or os.environ.get("PIGE360_PROJECT_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[2]


def read_json(path: Path, *, required: bool = True) -> dict[str, Any]:
    if not path.is_file():
        if required:
            raise FileNotFoundError(f"evidencia obrigatoria ausente: {path}")
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON deve conter um objeto: {path}")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _top_level_yaml_keys(path: Path, section: str) -> list[str]:
    """Le chaves diretas de uma secao YAML sem exigir engine Docker/PyYAML."""
    if not path.is_file():
        return []
    in_section = False
    keys: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if not raw.startswith((" ", "\t")):
            in_section = raw.strip() == f"{section}:"
            continue
        if not in_section:
            continue
        match = re.match(r"^  ([A-Za-z0-9_.-]+):(?:\s|$)", raw)
        if match:
            keys.append(match.group(1))
    return keys


def inventory_tree(root: Path) -> dict[str, Any]:
    app_names = sorted(
        path.parent.name
        for path in (root / "apps").glob("*/package.json")
        if path.is_file()
    )
    workflows = sorted(
        path.relative_to(root).as_posix()
        for pattern in ("*.yml", "*.yaml")
        for path in (root / ".github/workflows").glob(pattern)
        if path.is_file()
    )
    compose_path = root / "compose.yaml"
    compose_services = _top_level_yaml_keys(compose_path, "services")
    vue_javascript = sorted(
        path.relative_to(root).as_posix()
        for path in (root / "apps").rglob("*.vue.js")
        if path.is_file()
    )
    main_javascript = sorted(
        path.relative_to(root).as_posix()
        for path in (root / "apps").glob("*/src/main.js")
        if path.is_file()
    )
    return {
        "applications": {"count": len(app_names), "names": app_names},
        "workflows": {"count": len(workflows), "files": workflows},
        "compose": {
            "definition": compose_path.relative_to(root).as_posix(),
            "services_count": len(compose_services),
            "services": compose_services,
            "validation_scope": "declarative_inventory",
            "runtime_executed": False,
        },
        "source_compatibility": {
            "vue_js_count": len(vue_javascript),
            "vue_js_files": vue_javascript,
            "main_js_count": len(main_javascript),
            "main_js_files": main_javascript,
        },
    }


def requirements_summary(root: Path) -> dict[str, Any]:
    path = root / "docs/execution/requirements.json"
    ledger = read_json(path)
    requirements = ledger.get("requirements")
    if not isinstance(requirements, list):
        raise ValueError(f"ledger sem lista requirements: {path}")
    calculated = dict(sorted(Counter(str(item.get("status", "UNSPECIFIED")) for item in requirements).items()))
    cached = ledger.get("status_summary") if isinstance(ledger.get("status_summary"), dict) else {}
    return {
        "source": path.relative_to(root).as_posix(),
        "requirements_count": len(requirements),
        "status_summary": calculated,
        "cached_count": ledger.get("count"),
        "cached_status_summary": cached,
        "cache_matches_records": ledger.get("count") == len(requirements) and cached == calculated,
        "calculation": "recounted_from_requirements_records",
    }


def _network_sources(root: Path) -> list[dict[str, Any]]:
    candidates = [
        "release/reports/local-ci-report.json",
        "release/reports/build-report.json",
        "release/toolchain-inventory.json",
        "docs/execution/evidence/branding-import-report.json",
    ]
    result: list[dict[str, Any]] = []
    for relative in candidates:
        path = root / relative
        data = read_json(path, required=False)
        if "network_used" not in data:
            continue
        result.append(
            {
                "source": relative,
                "network_used": bool(data["network_used"]),
                "source_detail": data.get("network_usage_source"),
            }
        )
    return result


def network_evidence(root: Path) -> dict[str, Any]:
    sources = _network_sources(root)
    if not sources:
        return {"network_used": None, "status": "not_reported", "sources": []}
    used = any(item["network_used"] for item in sources)
    return {
        "network_used": used,
        "status": "reported_used" if used else "reported_not_used",
        "sources": sources,
    }


def _find_command(report: dict[str, Any], name: str) -> dict[str, Any] | None:
    for item in report.get("commands", []):
        if isinstance(item, dict) and item.get("name") == name:
            return item
    return None


def collect_evidence(root: Path) -> dict[str, Any]:
    tests = read_json(root / "release/reports/test-report.json")
    ci = read_json(root / "release/reports/local-ci-report.json")
    build = read_json(root / "release/reports/build-report.json")
    openapi = read_json(root / "docs/api/OPENAPI_REPORT.json")
    visual = read_json(root / "packages/visual-testing/baselines/visual-baseline-manifest.json")
    visual_report = read_json(root / "docs/design/visual-regression-report.json", required=False)
    backup = read_json(root / "release/artifacts/backup-restore/report.json")
    tree = inventory_tree(root)
    version = (root / "VERSION").read_text(encoding="utf-8").strip()
    oci_candidates = sorted((root / "release/artifacts/oci").glob("*-images-digests.json"))
    oci = read_json(oci_candidates[-1], required=False) if oci_candidates else {}
    oci_images = oci.get("images") if isinstance(oci.get("images"), list) else []
    runtime_executable = bool(oci.get("runtime_build_executed")) and bool(oci_images) and all(
        item.get("runtime_executable") is True for item in oci_images if isinstance(item, dict)
    )
    visual_records = visual.get("records") if isinstance(visual.get("records"), list) else []
    screens = sorted({str(item.get("screen")) for item in visual_records if item.get("screen")})
    pixel_result = visual_report.get("pixel_differences")
    pixel_regression_executed = pixel_result is not None or bool(
        build.get("builds", {}).get("visual", {}).get("pixel_regression_executed")
    )
    commands = ci.get("commands") if isinstance(ci.get("commands"), list) else []
    pytest_command = _find_command(ci, "pytest")
    frontend_command = _find_command(ci, "frontend-build")
    backup_command = _find_command(ci, "backup-restore")
    visual_command = _find_command(ci, "visual-contract")
    return {
        "version": version,
        "ci": {
            "status": ci.get("status", "unknown"),
            "checks_count": len(commands),
            "commands": commands,
            "pytest_command_status": pytest_command.get("status") if pytest_command else "not_reported",
            "frontend_build_status": frontend_command.get("status") if frontend_command else "not_reported",
            "backup_test_status": backup_command.get("status") if backup_command else "not_reported",
            "remote_operations_executed": ci.get("remote_operations_executed"),
        },
        "tests": {
            "status": tests.get("status", "unknown"),
            "pytest_passed": tests.get("pytest_passed"),
            "checks_count": len(tests.get("checks", [])) if isinstance(tests.get("checks"), list) else 0,
            "scope": "local_test_execution",
        },
        "openapi": {
            "paths": openapi.get("paths"),
            "operations": openapi.get("operations"),
            "schemas": openapi.get("schemas"),
            "duplicate_operation_ids": openapi.get("duplicate_operation_ids", []),
        },
        "tree": tree,
        "builds": build.get("builds", {}),
        "visual": {
            "baseline_kind": visual.get("baseline_kind", "unspecified"),
            "screens": len(screens),
            "screenshots": len(visual_records),
            "baseline_integrity_validated": bool(visual_command and visual_command.get("status") == "passed"),
            "pixel_regression_executed": pixel_regression_executed,
            "pixel_differences": pixel_result,
            "scope": "baseline_catalog_and_integrity",
        },
        "backup_restore": {
            "status": backup.get("status", "unknown"),
            "fixture": "local_sqlite_and_filesystem_synthetic_tenants",
            "tenant_restored": backup.get("tenant_restored"),
            "backup_sha256": backup.get("backup_sha256"),
            "cross_tenant_leakage": backup.get("cross_tenant_leakage"),
            "postgresql_restore_homologated": False,
            "minio_restore_homologated": False,
            "scope": "local_synthetic_test",
        },
        "oci": {
            "status": "structural_only" if oci else "not_generated",
            "images_count": len(oci_images),
            "runtime_engine_available": oci.get("runtime_engine_available"),
            "runtime_build_executed": oci.get("runtime_build_executed"),
            "runtime_executable": runtime_executable,
            "scope": "oci_layout_structural_only" if oci else "not_generated",
        },
        "network": network_evidence(root),
        "requirements": requirements_summary(root),
        "validation_classes": {
            "local_test_execution": "comando executado neste workspace e retorno registrado",
            "structural_validation": "contrato, arquivo ou manifesto inspecionado sem executar o runtime alvo",
            "external_homologation": "exige ambiente, credenciais e protocolo externos; nao inferida de testes locais",
        },
    }


def parse_input_specs(specs: Iterable[str] | None) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for spec in specs or []:
        key, separator, value = spec.partition("=")
        if not separator or not key.strip() or not value.strip():
            raise ValueError(f"entrada invalida; use chave=/caminho: {spec}")
        result[key.strip()] = Path(value).expanduser().resolve()
    env_map = {
        "canonical_base": "PIGE360_CANONICAL_BASE_ARCHIVE",
        "previous_attachment": "PIGE360_PREVIOUS_BASE_ARCHIVE",
        "architectural_reference": "PIGE360_ARCHITECTURAL_REFERENCE_ARCHIVE",
    }
    for key, env_name in env_map.items():
        if key not in result and os.environ.get(env_name):
            result[key] = Path(os.environ[env_name]).expanduser().resolve()
    input_root = os.environ.get("PIGE360_INPUT_ROOT")
    if input_root:
        result["input_root"] = Path(input_root).expanduser().resolve()
    return result


def _external_input(
    key: str,
    metadata: dict[str, Any],
    paths: dict[str, Path],
) -> dict[str, Any]:
    expected = metadata.get("sha256")
    path = paths.get(key)
    if path is None and paths.get("input_root") and metadata.get("name"):
        candidate = paths["input_root"] / str(metadata["name"])
        if candidate.is_file():
            path = candidate
    record: dict[str, Any] = {
        "key": key,
        "name": metadata.get("name"),
        "role": metadata.get("role"),
        "recorded_sha256": expected,
        "source": "docs/operations/SOURCE_BASELINE.json",
    }
    if path is None or not path.is_file():
        record.update({"sha256": expected, "verification": "recorded_digest_not_recomputed_in_this_run"})
        return record
    actual = sha256_file(path)
    if expected and actual != expected:
        raise ValueError(f"hash divergente para {key}: esperado {expected}, calculado {actual}")
    record.update(
        {
            "sha256": actual,
            "bytes": path.stat().st_size,
            "verification": "sha256_recomputed_from_file",
        }
    )
    return record


def collect_inputs(root: Path, specs: Iterable[str] | None = None) -> dict[str, Any]:
    paths = parse_input_specs(specs)
    baseline_path = root / "docs/operations/SOURCE_BASELINE.json"
    baseline = read_json(baseline_path)
    prompt = root / "PROMPT_FINAL_COMPLETO_PIGE360_V8_LOCAL_SEM_REPOSITORIO.md"
    branding = root / "docs/design/reference-assets/originals/PIGE360_BRANDING_COMPLETO.zip"
    records = [
        {
            "key": "implementation_contract",
            "name": prompt.name,
            "sha256": sha256_file(prompt),
            "bytes": prompt.stat().st_size,
            "verification": "sha256_recomputed_from_file",
        },
        {
            "key": "source_baseline_record",
            "name": baseline_path.relative_to(root).as_posix(),
            "sha256": sha256_file(baseline_path),
            "bytes": baseline_path.stat().st_size,
            "verification": "sha256_recomputed_from_file",
        },
    ]
    if branding.is_file():
        records.append(
            {
                "key": "branding_archive",
                "name": branding.relative_to(root).as_posix(),
                "sha256": sha256_file(branding),
                "bytes": branding.stat().st_size,
                "verification": "sha256_recomputed_from_file",
            }
        )
    records.extend(
        [
            _external_input("canonical_base", baseline.get("canonical_base", {}), paths),
            _external_input(
                "previous_attachment",
                baseline.get("previous_attachment_comparison", {}),
                paths,
            ),
            _external_input(
                "architectural_reference",
                baseline.get("architectural_reference_only", {}),
                paths,
            ),
        ]
    )
    canonical = baseline.get("canonical_base", {})
    source_revision = canonical.get("archive_comment_source_revision")
    return {
        "records": records,
        "source_baseline": baseline,
        "source_revision": {
            "value": source_revision,
            "origin": "zip_archive_comment" if source_revision else "not_recorded",
            "vcs_checkout_verified": False,
            "vcs_commit_claimed": False,
        },
    }


def report_time_bounds(ci: dict[str, Any]) -> tuple[str | None, str | None]:
    commands = ci.get("commands") if isinstance(ci.get("commands"), list) else []
    starts = sorted(str(item["started_at"]) for item in commands if isinstance(item, dict) and item.get("started_at"))
    finishes = sorted(str(item["finished_at"]) for item in commands if isinstance(item, dict) and item.get("finished_at"))
    return (starts[0] if starts else None, finishes[-1] if finishes else None)
