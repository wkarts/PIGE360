#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from evidence_common import (
    collect_evidence,
    collect_inputs,
    project_root,
    read_json,
    report_time_bounds,
    sha256_file,
)


def _dependency(record: dict[str, Any]) -> dict[str, Any] | None:
    digest = record.get("sha256")
    name = record.get("name")
    if not digest or not name:
        return None
    annotations = {
        "verification": record.get("verification"),
        "role": record.get("role"),
        "recorded_sha256": record.get("recorded_sha256"),
    }
    return {
        "uri": f"file:{name}",
        "digest": {"sha256": digest},
        "annotations": {key: value for key, value in annotations.items() if value is not None},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--subjects-json")
    parser.add_argument("--output")
    parser.add_argument("--root", help="raiz alternativa; tambem aceita PIGE360_PROJECT_ROOT")
    parser.add_argument(
        "--input",
        action="append",
        default=[],
        help="recalcula entrada externa no formato canonical_base=/caminho",
    )
    args = parser.parse_args()
    root = project_root(args.root)
    version = (root / "VERSION").read_text(encoding="utf-8").strip()
    output = args.output or f"release/PIGE360-{version}-source-provenance.intoto.json"
    if args.subjects_json:
        subjects = json.loads(Path(args.subjects_json).read_text(encoding="utf-8"))
    else:
        source_manifest = root / "release/source-tree-manifest.json"
        subjects = [{"name": "pige360-source-tree", "digest": {"sha256": sha256_file(source_manifest)}}]
    if not isinstance(subjects, list):
        raise ValueError("--subjects-json deve conter uma lista")

    evidence = collect_evidence(root)
    inputs = collect_inputs(root, args.input)
    ci_report = read_json(root / "release/reports/local-ci-report.json")
    resolved_dependencies = [item for record in inputs["records"] if (item := _dependency(record))]
    byproduct_paths = [
        root / "release/reports/local-ci-report.json",
        root / "release/reports/test-report.json",
        root / "release/reports/build-report.json",
        root / "release/toolchain-inventory.json",
        root / "docs/operations/BEFORE_AFTER_REPORT.json",
    ]
    byproducts = [
        {
            "name": path.relative_to(root).as_posix(),
            "digest": {"sha256": sha256_file(path)},
        }
        for path in byproduct_paths
        if path.is_file()
    ]
    started, finished = report_time_bounds(ci_report)
    now = datetime.now(timezone.utc).isoformat()
    invocation_material = json.dumps(
        {
            "version": version,
            "subjects": subjects,
            "dependencies": resolved_dependencies,
            "byproducts": byproducts,
            "started": started,
            "finished": finished,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    invocation_id = str(uuid.uuid5(uuid.NAMESPACE_URL, "pige360:" + hashlib.sha256(invocation_material.encode()).hexdigest()))
    remote_executed = evidence["ci"]["remote_operations_executed"]
    statement = {
        "_type": "https://in-toto.io/Statement/v1",
        "subject": subjects,
        "predicateType": "https://slsa.dev/provenance/v1",
        "predicate": {
            "buildDefinition": {
                "buildType": "https://pige360.local/build/v8",
                "externalParameters": {
                    "version": version,
                    "mode": "local-workspace",
                    "network": evidence["network"],
                    "remote_operations_executed": remote_executed,
                },
                "internalParameters": {
                    "workspace": ".",
                    "vcs_commit": None,
                    "source_revision": inputs["source_revision"],
                    "network_used": evidence["network"]["network_used"],
                    "network_usage_source": evidence["network"]["status"],
                },
                "resolvedDependencies": resolved_dependencies,
            },
            "runDetails": {
                "builder": {"id": "local://pige360/release-tooling"},
                "metadata": {
                    "invocationId": invocation_id,
                    "startedOn": started or now,
                    "finishedOn": finished or now,
                },
                "byproducts": byproducts,
            },
        },
    }
    out = Path(output)
    if not out.is_absolute():
        out = root / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(statement, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "generated", "output": str(out), "subjects": len(subjects)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
