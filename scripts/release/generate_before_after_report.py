#!/usr/bin/env python3
"""Gera comparacao rastreavel entre a base extraida e a arvore evoluida."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from evidence_common import project_root, read_json, sha256_file


EXCLUDED_PARTS = {
    ".git",
    ".continua-ai",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".toolchains",
    ".venv",
    "__pycache__",
    "coverage",
    "dist",
    "node_modules",
    "release-output",
    "runtime-data",
    "runtime-secrets",
    "target",
    "venv",
}
EXCLUDED_ROOT_PREFIXES = {
    ("release", ".openapi-runtime"),
    ("release", "artifacts"),
    ("release", "evidence"),
    ("release", "output"),
    ("release", "reports"),
}
EXCLUDED_RELEASE_FILES = {
    "release/final-tree.txt",
    "release/package-subjects.json",
    "release/packages-final.json",
    "release/packages-preliminary.json",
    "release/project-validation.json",
    "release/secret-scan-report.json",
    "release/source-tree-manifest.json",
    "release/toolchain-inventory.json",
}
SELF_OUTPUTS = {
    "docs/operations/BEFORE_AFTER_REPORT.json",
    "docs/operations/BEFORE_AFTER_REPORT.md",
    "docs/operations/FINAL_LOCAL_VALIDATION.md",
    "docs/operations/LOCAL_EXECUTION_REPORT.md",
}


def category(path: str) -> str:
    if path.startswith("backend/"):
        return "backend"
    if path.startswith(("apps/", "packages/", "types/")):
        return "frontend_and_apps"
    if path.startswith(("deploy/", "infra/", "compose.")):
        return "deployment_and_infrastructure"
    if path.startswith("rust/"):
        return "rust_and_native_core"
    if path.startswith(
        (
            ".github/workflows/",
            "CI_CD_KIT_LOCAL/",
            "scripts/build-farm/",
            "scripts/ci/",
            "scripts/desktop/",
            "scripts/mobile/",
            "scripts/oci/",
            "scripts/release/",
            "scripts/supply-chain/",
            "scripts/validation/",
        )
    ):
        return "ci_release_and_validation"
    if path.startswith("docs/"):
        return "documentation_and_evidence"
    if path.startswith("scripts/"):
        return "automation"
    return "project_root_and_other"


def source_inventory(root: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(root)
        name = relative.as_posix()
        generated_release = (
            any(relative.parts[: len(prefix)] == prefix for prefix in EXCLUDED_ROOT_PREFIXES)
            or name in EXCLUDED_RELEASE_FILES
            or (
                relative.parts[:1] == ("release",)
                and relative.name.startswith("PIGE360-")
                and relative.suffix == ".json"
            )
        )
        if name in SELF_OUTPUTS or generated_release or any(part in EXCLUDED_PARTS for part in relative.parts):
            continue
        if path.suffix in {".pyc", ".pyo", ".tsbuildinfo"}:
            continue
        files[name] = sha256_file(path)
    return files


def inventory_sha256(files: dict[str, str]) -> str:
    material = "".join(f"{digest}  {path}\n" for path, digest in sorted(files.items()))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _group(paths: list[str]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for path in paths:
        grouped[category(path)].append(path)
    return {area: sorted(values) for area, values in sorted(grouped.items())}


def _preservation(
    baseline: dict[str, str],
    current: dict[str, str],
    predicate: Any,
) -> dict[str, Any]:
    before = sorted(path for path in baseline if predicate(path))
    after = sorted(path for path in current if predicate(path))
    removed = sorted(set(before) - set(after))
    added = sorted(set(after) - set(before))
    modified = sorted(path for path in set(before) & set(after) if baseline[path] != current[path])
    return {
        "baseline_count": len(before),
        "current_count": len(after),
        "preserved_path_count": len(set(before) & set(after)),
        "removed": removed,
        "added": added,
        "modified": modified,
        "status": "preserved" if not removed else "removed_paths_detected",
    }


def compare_trees(baseline_root: Path, current_root: Path) -> dict[str, Any]:
    baseline = source_inventory(baseline_root)
    current = source_inventory(current_root)
    baseline_paths = set(baseline)
    current_paths = set(current)
    added = sorted(current_paths - baseline_paths)
    removed = sorted(baseline_paths - current_paths)
    modified = sorted(path for path in baseline_paths & current_paths if baseline[path] != current[path])
    unchanged = sorted(path for path in baseline_paths & current_paths if baseline[path] == current[path])
    states = {"added": added, "modified": modified, "removed": removed}
    by_area: dict[str, dict[str, Any]] = {}
    all_areas = sorted({category(path) for values in states.values() for path in values})
    grouped_states = {state: _group(paths) for state, paths in states.items()}
    for area in all_areas:
        by_area[area] = {}
        for state in ("added", "modified", "removed"):
            paths = grouped_states[state].get(area, [])
            by_area[area][state] = {"count": len(paths), "files": paths}
    baseline_record = read_json(current_root / "docs/operations/SOURCE_BASELINE.json", required=False)
    canonical = baseline_record.get("canonical_base", {})
    reference = baseline_record.get("architectural_reference_only", {})
    vue_js = _preservation(baseline, current, lambda path: path.endswith(".vue.js"))
    main_js = _preservation(
        baseline,
        current,
        lambda path: path.startswith("apps/") and path.endswith("/src/main.js"),
    )
    preservation_ok = not removed and vue_js["status"] == "preserved" and main_js["status"] == "preserved"
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "comparison_basis": {
            "baseline_directory_supplied_at_generation": True,
            "baseline_archive_name": canonical.get("name"),
            "baseline_archive_sha256": canonical.get("sha256"),
            "source_revision": {
                "value": canonical.get("archive_comment_source_revision"),
                "origin": "zip_archive_comment",
                "vcs_checkout_verified": False,
            },
            "architectural_reference": {
                "name": reference.get("name"),
                "sha256": reference.get("sha256"),
                "role": reference.get("role"),
                "used_as_product_base": False,
                "product_files_copied_or_substituted": False,
            },
            "ignored_generated_parts": sorted(EXCLUDED_PARTS),
            "ignored_release_generated_prefixes": ["/".join(value) for value in sorted(EXCLUDED_ROOT_PREFIXES)],
            "ignored_release_generated_files": sorted(EXCLUDED_RELEASE_FILES),
            "baseline_tree_sha256": inventory_sha256(baseline),
            "current_tree_sha256": inventory_sha256(current),
        },
        "summary": {
            "baseline_files": len(baseline),
            "current_files": len(current),
            "added": len(added),
            "modified": len(modified),
            "removed": len(removed),
            "unchanged": len(unchanged),
            "original_files_removed": bool(removed),
            "preservation_status": "passed" if preservation_ok else "failed",
        },
        "by_area": by_area,
        "all_removed_files": removed,
        "source_compatibility": {"vue_js": vue_js, "main_js": main_js},
        "interpretation": {
            "added": "arquivo inexistente na base e presente na arvore atual",
            "modified": "mesmo caminho com SHA-256 diferente",
            "removed": "caminho presente na base e ausente na arvore atual",
            "unchanged": "mesmo caminho e mesmo SHA-256",
        },
    }


def markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Relatorio antes/depois da evolucao conservadora",
        "",
        "A comparacao usa caminhos e SHA-256 dos arquivos-fonte. Diretorios de build, caches,",
        "dependencias instaladas e artefatos de release sao excluidos para nao misturar produto com lixo gerado.",
        "A revisao informada abaixo vem do comentario do ZIP; ela nao e apresentada como checkout Git verificado.",
        "",
        "## Base rastreada",
        "",
        f"- ZIP: `{report['comparison_basis'].get('baseline_archive_name')}`",
        f"- SHA-256: `{report['comparison_basis'].get('baseline_archive_sha256')}`",
        f"- Revisao declarada no comentario do ZIP: `{report['comparison_basis']['source_revision'].get('value')}`",
        "- Checkout Git verificado: **nao**",
        "- Papel: **unica base do produto nesta evolucao**",
        "",
        "## Referencia arquitetural",
        "",
        f"- Arquivo: `{report['comparison_basis']['architectural_reference'].get('name')}`",
        f"- SHA-256: `{report['comparison_basis']['architectural_reference'].get('sha256')}`",
        "- Uso: referencia de padroes administrativos; **nao** foi usada como base, nem para copiar ou substituir o produto PIGE360.",
        "",
        "## Resumo",
        "",
        "| Medida | Quantidade |",
        "|---|---:|",
        f"| Arquivos na base | {summary['baseline_files']} |",
        f"| Arquivos na arvore atual | {summary['current_files']} |",
        f"| Adicionados | {summary['added']} |",
        f"| Modificados | {summary['modified']} |",
        f"| Removidos | {summary['removed']} |",
        f"| Inalterados | {summary['unchanged']} |",
        "",
        f"Preservacao da base: **{summary['preservation_status']}**.",
        "",
        "## Compatibilidade Vue/JavaScript preservada",
        "",
        "| Familia | Base | Atual | Caminhos preservados | Removidos |",
        "|---|---:|---:|---:|---:|",
    ]
    for label, key in (("`*.vue.js`", "vue_js"), ("`apps/*/src/main.js`", "main_js")):
        item = report["source_compatibility"][key]
        lines.append(
            f"| {label} | {item['baseline_count']} | {item['current_count']} | "
            f"{item['preserved_path_count']} | {len(item['removed'])} |"
        )
    lines.extend(["", "## Alteracoes por area", ""])
    for area, states in report["by_area"].items():
        lines.extend(
            [
                f"### {area}",
                "",
                "| Estado | Quantidade |",
                "|---|---:|",
                f"| Adicionados | {states['added']['count']} |",
                f"| Modificados | {states['modified']['count']} |",
                f"| Removidos | {states['removed']['count']} |",
                "",
            ]
        )
        for state, title in (("added", "Adicionados"), ("modified", "Modificados"), ("removed", "Removidos")):
            paths = states[state]["files"]
            if not paths:
                continue
            lines.extend([f"#### {title}", ""])
            lines.extend(f"- `{path}`" for path in paths)
            lines.append("")
    if not report["all_removed_files"]:
        lines.extend(["## Remocoes", "", "Nenhum arquivo-fonte da base foi removido.", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--baseline-dir",
        default=os.environ.get("PIGE360_BASELINE_TREE"),
        help="arvore extraida da base; tambem aceita PIGE360_BASELINE_TREE",
    )
    parser.add_argument("--current-dir", default=os.environ.get("PIGE360_PROJECT_ROOT"))
    parser.add_argument("--json-output", default="docs/operations/BEFORE_AFTER_REPORT.json")
    parser.add_argument("--markdown-output", default="docs/operations/BEFORE_AFTER_REPORT.md")
    parser.add_argument("--fail-on-removal", action="store_true")
    parser.add_argument(
        "--verify-current",
        action="store_true",
        help="confere se o digest da arvore atual ainda coincide com o relatorio existente",
    )
    args = parser.parse_args()
    root = project_root(args.current_dir)
    json_output = Path(args.json_output)
    if not json_output.is_absolute():
        json_output = root / json_output
    if args.verify_current:
        report = read_json(json_output)
        recorded = report.get("comparison_basis", {}).get("current_tree_sha256")
        current = source_inventory(root)
        actual = inventory_sha256(current)
        passed = bool(recorded) and recorded == actual
        print(
            json.dumps(
                {
                    "status": "passed" if passed else "failed",
                    "recorded_current_tree_sha256": recorded,
                    "actual_current_tree_sha256": actual,
                    "current_files": len(current),
                },
                ensure_ascii=False,
            )
        )
        return 0 if passed else 1
    if not args.baseline_dir:
        parser.error("informe --baseline-dir ou PIGE360_BASELINE_TREE")
    baseline = Path(args.baseline_dir).expanduser().resolve()
    if not baseline.is_dir():
        parser.error(f"arvore base inexistente: {baseline}")
    report = compare_trees(baseline, root)
    markdown_output = Path(args.markdown_output)
    if not markdown_output.is_absolute():
        markdown_output = root / markdown_output
    json_output.parent.mkdir(parents=True, exist_ok=True)
    markdown_output.parent.mkdir(parents=True, exist_ok=True)
    json_output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_output.write_text(markdown(report), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": report["summary"]["preservation_status"],
                "json": str(json_output),
                "markdown": str(markdown_output),
                **{key: report["summary"][key] for key in ("added", "modified", "removed", "unchanged")},
            },
            ensure_ascii=False,
        )
    )
    return 1 if args.fail_on_removal and report["summary"]["removed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
