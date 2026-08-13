#!/usr/bin/env python3
"""Registra conservadoramente o vínculo operacional de NFS-e para serviços."""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
JSON_PATH = ROOT / "docs/execution/requirements.json"
MATRIX_PATH = ROOT / "docs/execution/REQUIREMENTS_MATRIX.md"


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def markdown(value: Any) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", "<br>")


def main() -> int:
    data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    requirements = data["requirements"]
    by_id = {item["id"]: item for item in requirements}
    target = by_id["V8-1608"]
    target.update(
        status="TESTING",
        implementation=(
            "O evento fiscal de cada item tributável de serviço passa a referenciar a montagem e a NFS-e "
            "geradas pelo roteamento; estados do provider e o cancelamento local são refletidos no evento e no pedido sem simular autorização externa."
        ),
        tests=(
            "Foram adicionados testes de migration e de rastreabilidade pedido → evento → montagem → NFS-e → "
            "aguardo de configuração do provider → cancelamento local, incluindo repetição idempotente. A execução Pytest permanece pendente porque a dependência não existe no ambiente."
        ),
        evidence="docs/execution/evidence/service-nfse-traceability-0042.json",
        related_files="; ".join(
            [
                "backend/app/modules/fiscal/application/document_routing_service.py",
                "backend/app/shared/events/handlers.py",
                "backend/app/shared/database/operational_schema.sql",
                "backend/app/shared/database/store.py",
                "backend/app/shared/database/models_tenant.py",
                "backend/alembic_tenant/versions/0042_service_fiscal_document_linkage.py",
                "apps/tenant-admin-web/src/components/ServicesPanel.vue",
                "backend/tests/fiscal/test_fiscal_document_routing_assembly.py",
                "backend/tests/migrations/test_service_fiscal_document_linkage_migration.py",
                "docs/services/SERVICE_NFSE_TRACEABILITY.md",
            ]
        ),
    )

    counts = Counter(item["status"] for item in requirements)
    data["generated_at"] = now()
    data["count"] = len(requirements)
    data["status_summary"] = dict(sorted(counts.items()))
    JSON_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    fields = [
        "id", "section", "description", "module", "dependencies", "related_files", "status",
        "implementation", "tests", "evidence", "observations",
    ]
    lines = [
        "# Matriz persistente de requisitos V8",
        "",
        "Esta matriz foi extraída do contrato integral e deve ser atualizada somente com evidência executável. Estados permitidos: `NOT_STARTED`, `IMPLEMENTING`, `IMPLEMENTED`, `TESTING`, `VERIFIED`, `BLOCKED_EXTERNAL`, `NOT_APPLICABLE`.",
        "",
        f"Atualizada em `{data['generated_at']}` após o incremento 0042 de rastreabilidade de NFS-e para serviços.",
        "",
        "## Resumo de estados",
        "",
        "| Estado | Quantidade |",
        "|---|---:|",
        *[f"| {status} | {counts[status]} |" for status in sorted(counts)],
        "",
        "| ID | Seção de origem | Descrição | Módulo | Dependências | Arquivos relacionados | Status | Implementação | Testes | Evidência | Observações |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    lines.extend("| " + " | ".join(markdown(item.get(field)) for field in fields) + " |" for item in requirements)
    MATRIX_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"updated": ["V8-1608"], "status_summary": data["status_summary"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
