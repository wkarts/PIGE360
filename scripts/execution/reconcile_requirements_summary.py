#!/usr/bin/env python3
"""Sincroniza somente o resumo do ledger V8, sem promover requisitos."""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
JSON_PATH = ROOT / "docs/execution/requirements.json"
MATRIX_PATH = ROOT / "docs/execution/REQUIREMENTS_MATRIX.md"


def main() -> int:
    document = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    requirements = document.get("requirements")
    if not isinstance(requirements, list):
        raise RuntimeError("requirements.json não contém a lista requirements")
    counts = dict(sorted(Counter(str(item.get("status")) for item in requirements).items()))
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    document["count"] = len(requirements)
    document["status_summary"] = counts
    document["generated_at"] = generated_at
    JSON_PATH.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    matrix = MATRIX_PATH.read_text(encoding="utf-8")
    table_marker = "| ID | Seção de origem |"
    marker_index = matrix.find(table_marker)
    if marker_index < 0:
        raise RuntimeError("Cabeçalho da tabela de requisitos não encontrado")
    requirements_table = matrix[marker_index:]
    summary_rows = "\n".join(f"| {status} | {count} |" for status, count in counts.items())
    header = (
        "# Matriz persistente de requisitos V8\n\n"
        "Esta matriz foi extraída do contrato integral e deve ser atualizada somente com evidência executável. "
        "Estados permitidos: `NOT_STARTED`, `IMPLEMENTING`, `IMPLEMENTED`, `TESTING`, `VERIFIED`, "
        "`BLOCKED_EXTERNAL`, `NOT_APPLICABLE`.\n\n"
        f"Resumo reconciliado em `{generated_at}` diretamente dos {len(requirements)} registros; "
        "nenhum requisito foi promovido por esta operação.\n\n"
        "## Resumo de estados\n\n"
        "| Estado | Quantidade |\n"
        "|---|---:|\n"
        f"{summary_rows}\n\n"
    )
    MATRIX_PATH.write_text(header + requirements_table, encoding="utf-8")

    # Confirma que o corpo não sofreu perda nem duplicação durante a troca do cabeçalho.
    ids = re.findall(r"^\| (V8-\d{4}) \|", requirements_table, flags=re.MULTILINE)
    if len(ids) != len(requirements) or len(ids) != len(set(ids)):
        raise RuntimeError("A matriz Markdown não preservou os IDs únicos do ledger")
    print(json.dumps({"count": len(requirements), "status_summary": counts}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
