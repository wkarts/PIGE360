#!/usr/bin/env python3
"""Registra conservadoramente o incremento auditável de recibos de serviços."""
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
    target = {item["id"]: item for item in requirements}["V8-1609"]
    target.update(
        status="TESTING",
        implementation=(
            "Pagamentos confirmados e PIX conciliados emitem recibo por pedido de serviço por meio do rateio em "
            "accounts_receivable.charge_id; o PDF tem snapshot congelado, SHA-256, storage privado por tenant, "
            "auditoria, outbox, consulta, download autenticado e anulação sem apagar o histórico financeiro."
        ),
        tests=(
            "Foram incluídos cenários de migration e de pagamento → recibo → download com hash → isolamento por tenant "
            "→ anulação → reemissão. A execução Pytest permanece pendente porque a dependência não existe no ambiente."
        ),
        evidence="docs/execution/evidence/service-payment-receipts-0043.json",
        related_files="; ".join(
            [
                "backend/app/modules/services/application/vertical_service.py",
                "backend/app/modules/services/presentation/vertical_schemas.py",
                "backend/app/modules/services/presentation/router.py",
                "backend/app/modules/finance/presentation/router.py",
                "backend/app/modules/banking/presentation/router.py",
                "backend/app/shared/database/operational_schema.sql",
                "backend/app/shared/database/models_tenant.py",
                "backend/alembic_tenant/versions/0043_service_payment_receipts.py",
                "apps/tenant-admin-web/src/components/ServicesPanel.vue",
                "backend/tests/finance/test_finance_banking_services.py",
                "backend/tests/migrations/test_service_payment_receipts_migration.py",
                "docs/services/SERVICE_PAYMENT_RECEIPTS.md",
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
        f"Atualizada em `{data['generated_at']}` após o incremento 0043 de recibos de pagamento para serviços.",
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
    print(json.dumps({"updated": ["V8-1609"], "status_summary": data["status_summary"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
