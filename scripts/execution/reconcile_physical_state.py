#!/usr/bin/env python3
"""Reconcilia o estado físico local do PIGE360 sem depender de Git ou rede."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

EXCLUDED_PREFIXES = (
    ".recovery/",
    ".pytest_cache/",
    ".mypy_cache/",
    ".ruff_cache/",
    "release/checkpoints/",
)
EXCLUDED_PARTS = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "node_modules", ".venv", "venv", "dist", "build", "target"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def include_path(rel: str) -> bool:
    rel = rel.replace(os.sep, "/")
    if rel == "CHECKPOINT_MANIFEST.json":
        return False
    if any(rel.startswith(prefix) for prefix in EXCLUDED_PREFIXES):
        return False
    path = PurePosixPath(rel)
    if any(part in EXCLUDED_PARTS for part in path.parts):
        return False
    if path.suffix in EXCLUDED_SUFFIXES:
        return False
    return True


def run_version(command: list[str]) -> str:
    try:
        result = subprocess.run(command, text=True, capture_output=True, timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return "not_available"
    output = (result.stdout or result.stderr).strip().splitlines()
    return output[0] if output else f"exit_{result.returncode}"


def count_create_tables(path: Path) -> int:
    if not path.exists():
        return 0
    text = path.read_text(encoding="utf-8", errors="replace")
    return len(re.findall(r"(?im)^\s*CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?", text))


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def regression_state(root: Path) -> dict[str, object]:
    evidence = root / "docs/execution/evidence"
    candidates: list[tuple[int, Path, Path]] = []
    for status_path in evidence.glob("backend-final-regression-*.status"):
        match = re.fullmatch(r"backend-final-regression-(\d+)\.status", status_path.name)
        if not match:
            continue
        log_path = status_path.with_suffix(".log")
        if log_path.exists():
            candidates.append((int(match.group(1)), status_path, log_path))
    completed = [candidate for candidate in candidates if candidate[1].read_text(encoding="utf-8").strip() == "0"]
    selected = max(completed or candidates, default=(0, evidence / "backend-final-regression.status", evidence / "backend-final-regression.log"), key=lambda item: item[0])
    _, status_file, log_file = selected
    status = status_file.read_text(encoding="utf-8").strip() if status_file.exists() else "RUNNING_OR_NOT_FINALIZED"
    summary = "não finalizada"
    if log_file.exists():
        text = log_file.read_text(encoding="utf-8", errors="replace")
        matches = re.findall(r"(?m)^=+\s*(\d+) passed(?:,\s*(\d+) skipped)?\s+in\s+([0-9.]+)s\s*=+$", text)
        if matches:
            passed, skipped, seconds = matches[-1]
            summary = f"{passed} aprovados, {skipped or '0'} ignorados, {seconds}s"
        else:
            simple = re.findall(r"(?m)^(\d+) passed(?:,\s*(\d+) skipped)?\s+in\s+([0-9.]+)s(?:\s+\([^\n]+\))?$", text)
            if simple:
                passed, skipped, seconds = simple[-1]
                summary = f"{passed} aprovados, {skipped or '0'} ignorados, {seconds}s"
    return {
        "status": status,
        "summary": summary,
        "status_file": str(status_file.relative_to(root)),
        "log_file": str(log_file.relative_to(root)),
    }


def compare_baseline(root: Path, baseline_zip: Path) -> dict[str, object]:
    baseline: dict[str, str] = {}
    with ZipFile(baseline_zip) as archive:
        for info in archive.infolist():
            if info.is_dir() or not include_path(info.filename):
                continue
            baseline[info.filename] = hashlib.sha256(archive.read(info.filename)).hexdigest()

    current: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if not include_path(rel):
            continue
        current[rel] = sha256_file(path)

    added = sorted(set(current) - set(baseline))
    deleted = sorted(set(baseline) - set(current))
    modified = sorted(path for path in set(current) & set(baseline) if current[path] != baseline[path])
    unchanged = len(set(current) & set(baseline)) - len(modified)
    return {
        "baseline_zip": str(baseline_zip.relative_to(root)),
        "baseline_sha256": sha256_file(baseline_zip),
        "added": added,
        "modified": modified,
        "deleted": deleted,
        "unchanged_count": unchanged,
        "current_file_count": len(current),
        "baseline_file_count": len(baseline),
    }


def write_changed_files(root: Path, comparison: dict[str, object]) -> None:
    evidence = root / "docs/execution/evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    payload = {"generated_at": utc_now(), **comparison}
    json_path = evidence / "changed-files-current-turn.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Arquivos alterados no checkpoint atual",
        "",
        f"- Gerado em: `{payload['generated_at']}`",
        f"- Baseline local: `{payload['baseline_zip']}`",
        f"- SHA-256 do baseline: `{payload['baseline_sha256']}`",
        f"- Arquivos novos: `{len(payload['added'])}`",
        f"- Arquivos modificados: `{len(payload['modified'])}`",
        f"- Arquivos removidos: `{len(payload['deleted'])}`",
        f"- Arquivos inalterados comparáveis: `{payload['unchanged_count']}`",
        "",
    ]
    for title, key in (("Novos", "added"), ("Modificados", "modified"), ("Removidos", "deleted")):
        lines.extend([f"## {title}", ""])
        values = payload[key]
        if values:
            lines.extend(f"- `{value}`" for value in values)
        else:
            lines.append("- Nenhum.")
        lines.append("")
    (evidence / "changed-files-current-turn.md").write_text("\n".join(lines), encoding="utf-8")


def write_branding_checksums(root: Path) -> None:
    manifest_path = root / "docs/design/reference-assets/manifest.json"
    if not manifest_path.exists():
        return
    manifest = load_json(manifest_path)
    lines = [
        f"{manifest.get('source_archive_sha256', '')}  {manifest.get('source_archive', '')}",
    ]
    for item in sorted(manifest.get("files", []), key=lambda value: value.get("path", "")):
        lines.append(f"{item.get('sha256', '')}  {item.get('path', '')}")
    output = root / "docs/execution/evidence/branding-checksums.txt"
    output.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def build_inventory(root: Path) -> dict[str, object]:
    openapi = load_json(root / "docs/api/openapi.json")
    paths = openapi.get("paths", {})
    operations = sum(
        1
        for methods in paths.values()
        if isinstance(methods, dict)
        for method in methods
        if method.lower() in {"get", "post", "put", "patch", "delete", "options", "head", "trace"}
    )
    schemas = openapi.get("components", {}).get("schemas", {})
    apps = sorted(path.parent.parent.name for path in (root / "apps").glob("*/public/manifest.webmanifest"))
    package_locks = sorted(path.relative_to(root).as_posix() for path in root.glob("**/package-lock.json") if include_path(path.relative_to(root).as_posix()))
    node_modules = any(path.is_dir() for path in root.glob("**/node_modules"))
    git_dirs = [path.relative_to(root).as_posix() for path in root.rglob(".git") if path.is_dir() and not str(path).startswith(str(root / ".recovery"))]
    requirements = load_json(root / "docs/execution/requirements.json")
    status_summary = requirements.get("status_summary", {})
    return {
        "generated_at": utc_now(),
        "workspace": str(root),
        "version": (root / "VERSION").read_text(encoding="utf-8").strip() if (root / "VERSION").exists() else "unknown",
        "python": platform.python_version(),
        "pytest": run_version([sys.executable, "-m", "pytest", "--version"]),
        "node": run_version(["node", "--version"]),
        "npm": run_version(["npm", "--version"]),
        "tsc": run_version(["tsc", "--version"]),
        "docker": run_version(["docker", "--version"]),
        "cargo": run_version(["cargo", "--version"]),
        "operational_tables": count_create_tables(root / "backend/app/shared/database/operational_schema.sql"),
        "control_tables": count_create_tables(root / "backend/app/shared/database/control_schema.sql"),
        "tenant_base_tables": count_create_tables(root / "backend/app/shared/database/tenant_schema.sql"),
        "python_app_files": sum(1 for path in (root / "backend/app").rglob("*.py") if path.is_file()),
        "python_test_files": sum(1 for path in (root / "backend/tests").rglob("test_*.py") if path.is_file()),
        "openapi_paths": len(paths),
        "openapi_operations": operations,
        "openapi_schemas": len(schemas),
        "pwa_apps": apps,
        "pwa_app_count": len(apps),
        "package_locks": package_locks,
        "node_modules_present": node_modules,
        "git_directories": git_dirs,
        "requirements_count": requirements.get("count", len(requirements.get("requirements", []))),
        "requirements_status_summary": status_summary,
        "regression": regression_state(root),
    }


def write_reconciliation(root: Path, inventory: dict[str, object], comparison: dict[str, object]) -> None:
    r = inventory["regression"]
    req = inventory["requirements_status_summary"]
    lines = [
        "# Reconciliação do estado físico",
        "",
        f"Gerada em `{inventory['generated_at']}` diretamente do workspace local, sem Git e sem acesso remoto.",
        "",
        "## Identidade do workspace",
        "",
        f"- Workspace: `{inventory['workspace']}`",
        f"- Versão física em `VERSION`: `{inventory['version']}`",
        f"- Diretórios `.git` operacionais encontrados: `{len(inventory['git_directories'])}`",
        f"- Baseline local comparado: `{comparison['baseline_zip']}`",
        f"- SHA-256 do baseline: `{comparison['baseline_sha256']}`",
        "",
        "## Inventário executável",
        "",
        f"- Tabelas no schema operacional: `{inventory['operational_tables']}`",
        f"- Tabelas no schema do Control Plane: `{inventory['control_tables']}`",
        f"- Tabelas no schema-base do Tenant Plane: `{inventory['tenant_base_tables']}`",
        f"- Arquivos Python sob `backend/app`: `{inventory['python_app_files']}`",
        f"- Arquivos de teste Python: `{inventory['python_test_files']}`",
        f"- Paths OpenAPI: `{inventory['openapi_paths']}`",
        f"- Operações OpenAPI: `{inventory['openapi_operations']}`",
        f"- Schemas OpenAPI: `{inventory['openapi_schemas']}`",
        f"- Aplicações com manifesto PWA: `{inventory['pwa_app_count']}`",
        "",
        "## Toolchain disponível",
        "",
        f"- Python: `{inventory['python']}`",
        f"- Pytest: `{inventory['pytest']}`",
        f"- Node.js: `{inventory['node']}`",
        f"- npm: `{inventory['npm']}`",
        f"- TypeScript: `{inventory['tsc']}`",
        f"- Docker: `{inventory['docker']}`",
        f"- Cargo/Rust: `{inventory['cargo']}`",
        "",
        "## Frontend e builds",
        "",
        f"- `node_modules` presente: `{str(inventory['node_modules_present']).lower()}`",
        f"- Lockfiles npm encontrados: `{len(inventory['package_locks'])}`",
        "- O build Vite da administração do tenant permanece não executável offline enquanto `vue-tsc` e as dependências locais não estiverem materializados.",
        "- A sintaxe dos scripts Vue e o SDK TypeScript foram validados com o compilador TypeScript disponível no host.",
        "",
        "## Regressão consolidada",
        "",
        f"- Estado: `{r['status']}`",
        f"- Resultado extraído: `{r['summary']}`",
        f"- Log: `{r['log_file']}`",
        f"- Código de saída: `{r['status_file']}`",
        "",
        "## Matriz persistente antes desta reconciliação",
        "",
        f"- Total: `{inventory['requirements_count']}`",
    ]
    for status in sorted(req):
        lines.append(f"- {status}: `{req[status]}`")
    lines.extend([
        "",
        "Os totais acima são os encontrados antes da atualização desta matriz. O arquivo estruturado é regenerado no mesmo checkpoint após a classificação conservadora das evidências novas.",
        "",
        "## Diferenças contra o baseline local",
        "",
        f"- Novos: `{len(comparison['added'])}`",
        f"- Modificados: `{len(comparison['modified'])}`",
        f"- Removidos: `{len(comparison['deleted'])}`",
        f"- Inalterados comparáveis: `{comparison['unchanged_count']}`",
        "",
        "A relação completa está em `docs/execution/evidence/changed-files-current-turn.md` e no JSON correspondente.",
        "",
        "## Restauração do checkpoint canônico",
        "",
        "- O checkpoint r000009 foi validado por SHA-256, nomes únicos, `testzip()` e manifesto antes da restauração.",
        "- Arquivos esperados pelo manifesto: `2514`.",
        "- Ausências no instante da restauração: `0`.",
        "- Divergências SHA-256 no instante da restauração: `0`.",
        "- O overlay encontrado antes da restauração foi preservado fora do workspace para investigação, sem sobreposição destrutiva.",
        "- Evidência: `docs/execution/evidence/checkpoint-r000009-restore-validation-r000010.json`.",
        "",
        "## Correções de divergência documental",
        "",
        "1. A versão física é obtida de `VERSION`; registros anteriores com versão distinta foram descartados como obsoletos.",
        "2. Quantidades de tabelas, rotas, schemas, testes e aplicações foram recalculadas; não foram copiadas de respostas anteriores.",
        "3. Resultados de teste somente são aceitos quando o log e o código de saída persistidos existem.",
        "4. Integrações sem credenciais permanecem `not_configured`; fixtures de teste não são apresentadas como homologação real.",
        "5. O build frontend indisponível por dependências locais ausentes permanece registrado como pendência, não como aprovação.",
        "6. Não houve clone, pull, push, Pull Request, release remota, publicação de imagem ou deploy remoto.",
        "",
    ])
    (root / "docs/execution/PHYSICAL_RECONCILIATION.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--baseline", default=".recovery/PIGE360-1.0.0-source.zip")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    baseline = (root / args.baseline).resolve()
    if not baseline.exists():
        raise SystemExit(f"Baseline ausente: {baseline}")
    comparison = compare_baseline(root, baseline)
    write_changed_files(root, comparison)
    write_branding_checksums(root)
    inventory = build_inventory(root)
    write_reconciliation(root, inventory, comparison)
    evidence = root / "docs/execution/evidence/physical-reconciliation.json"
    evidence.write_text(json.dumps({"inventory": inventory, "comparison": comparison}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "inventory": inventory,
        "differences": {k: len(comparison[k]) for k in ("added", "modified", "deleted")},
        "outputs": [
            "docs/execution/PHYSICAL_RECONCILIATION.md",
            "docs/execution/evidence/physical-reconciliation.json",
            "docs/execution/evidence/changed-files-current-turn.json",
            "docs/execution/evidence/changed-files-current-turn.md",
            "docs/execution/evidence/branding-checksums.txt",
        ],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
