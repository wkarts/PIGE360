#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from evidence_common import collect_evidence, collect_inputs, project_root, read_json, sha256_file


REMOTE_OPERATION_NAMES = (
    "code_hosting",
    "clone_sync",
    "authentication",
    "push",
    "tags",
    "release",
    "registry",
    "deploy",
    "pull_request",
)


def remote_operations(ci_report: dict[str, Any]) -> dict[str, Any]:
    detailed = ci_report.get("remote_operations")
    if isinstance(detailed, dict):
        operations = {name: detailed.get(name) for name in REMOTE_OPERATION_NAMES}
        source = "release/reports/local-ci-report.json:remote_operations"
    elif ci_report.get("remote_operations_executed") is False:
        operations = {name: False for name in REMOTE_OPERATION_NAMES}
        source = "release/reports/local-ci-report.json:remote_operations_executed"
    else:
        operations = {name: None for name in REMOTE_OPERATION_NAMES}
        source = "not_reported"
    return {"operations": operations, "source": source}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--packages-json")
    parser.add_argument("--output")
    parser.add_argument(
        "--input",
        action="append",
        default=[],
        help="recalcula entrada externa no formato canonical_base=/caminho",
    )
    parser.add_argument("--root", help="raiz alternativa; tambem aceita PIGE360_PROJECT_ROOT")
    args = parser.parse_args()
    root = project_root(args.root)
    version = (root / "VERSION").read_text(encoding="utf-8").strip()
    output = args.output or f"release/PIGE360-{version}-release-manifest.json"
    packages = json.loads(Path(args.packages_json).read_text(encoding="utf-8")) if args.packages_json else []
    if not isinstance(packages, list):
        raise ValueError("--packages-json deve conter uma lista")

    evidence = collect_evidence(root)
    input_evidence = collect_inputs(root, args.input)
    ci_report = read_json(root / "release/reports/local-ci-report.json")
    sbom = root / f"release/PIGE360-{version}-sbom.cdx.json"
    if not sbom.is_file():
        raise FileNotFoundError(f"SBOM obrigatorio ausente: {sbom}")
    oci_candidates = sorted((root / "release/artifacts/oci").glob("*-images-digests.json"))
    oci_report_path = oci_candidates[-1] if oci_candidates else None
    branding_report = read_json(
        root / "docs/execution/evidence/branding-import-report.json",
        required=False,
    )
    before_after = read_json(root / "docs/operations/BEFORE_AFTER_REPORT.json", required=False)
    remote = remote_operations(ci_report)
    tree = evidence["tree"]
    manifest = {
        "schema_version": 2,
        "product": "PIGE360",
        "full_name": "PIGE360 — Plataforma Integrada de Gestão Educacional",
        "version": version,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "workspace": ".",
        "construction_mode": "local_workspace",
        "network": evidence["network"],
        "network_used": evidence["network"]["network_used"],
        "remote_operations": remote["operations"],
        "remote_operations_evidence_source": remote["source"],
        "inputs": input_evidence["records"],
        "source_baseline": {
            "canonical_base": input_evidence["source_baseline"].get("canonical_base"),
            "source_revision": input_evidence["source_revision"],
            "note": "a revisao foi lida do comentario do ZIP; nao representa checkout Git verificado",
        },
        "evidence": {
            "pytest_passed": evidence["tests"]["pytest_passed"],
            "pytest_status": evidence["tests"]["status"],
            "local_checks": evidence["ci"]["checks_count"],
            "openapi_paths": evidence["openapi"]["paths"],
            "openapi_operations": evidence["openapi"]["operations"],
            "openapi_schemas": evidence["openapi"]["schemas"],
            "applications": tree["applications"]["count"],
            "application_names": tree["applications"]["names"],
            "compose_services": tree["compose"]["services_count"],
            "compose_service_names": tree["compose"]["services"],
            "workflows": tree["workflows"]["count"],
            "workflow_files": tree["workflows"]["files"],
            "visual_screens": evidence["visual"]["screens"],
            "screenshots": evidence["visual"]["screenshots"],
            "visual_scope": evidence["visual"],
            "backup_restore": evidence["backup_restore"],
            "oci": evidence["oci"],
            "requirements": evidence["requirements"],
            "validation_classes": evidence["validation_classes"],
            "source_compatibility": tree["source_compatibility"],
        },
        "build_status": evidence["builds"],
        "sbom": {
            "path": sbom.relative_to(root).as_posix(),
            "sha256": sha256_file(sbom),
            "format": "CycloneDX 1.6",
        },
        "oci": {
            **evidence["oci"],
            "report": oci_report_path.relative_to(root).as_posix() if oci_report_path else None,
            "report_sha256": sha256_file(oci_report_path) if oci_report_path else None,
            "warning": "layout OCI estrutural nao e imagem executavel nem smoke test de container",
        },
        "packages": packages,
        "integrations": [
            {"name": "PostgreSQL async", "status": "contract_and_migrations", "external_homologation": "not_executed"},
            {"name": "Redis/RabbitMQ/MinIO", "status": "compose_and_contracts", "external_homologation": "not_executed"},
            {"name": "Cloudflare", "status": "not_configured", "external_homologation": "not_executed"},
            {"name": "Mailcow", "status": "not_configured", "external_homologation": "not_executed"},
            {"name": "Evolution API", "status": "not_configured", "external_homologation": "not_executed"},
            {"name": "Fiscal SEFAZ/NFS-e", "status": "not_homologated", "external_homologation": "not_executed"},
            {"name": "GOV.BR", "status": "not_configured_conditional", "external_homologation": "not_executed"},
            {"name": "ICP-Brasil", "status": "provider_contract_only", "external_homologation": "not_executed"},
            {"name": "Play/App Store", "status": "workflow_contract", "external_homologation": "not_executed"},
        ],
        "branding_input": {
            "status": branding_report.get("status", "not_reported"),
            "archive_sha256": branding_report.get("archive_sha256"),
            "files_count": branding_report.get("files_count"),
            "internal_checksums_verified": branding_report.get("internal_checksums_verified"),
            "source": "docs/execution/evidence/branding-import-report.json",
        },
        "before_after": {
            "status": before_after.get("summary", {}).get("preservation_status", "not_generated"),
            "summary": before_after.get("summary"),
            "source": "docs/operations/BEFORE_AFTER_REPORT.json" if before_after else None,
        },
        "residual_risks_document": "docs/operations/RISK_REGISTER.md",
    }
    out = Path(output)
    if not out.is_absolute():
        out = root / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "generated", "output": str(out), "packages": len(packages)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
