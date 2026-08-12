#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
JSON_PATH = ROOT / "docs/execution/requirements.json"
MD_PATH = ROOT / "docs/execution/REQUIREMENTS_MATRIX.md"


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def esc(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("|", "\\|").replace("\n", "<br>")


def main() -> int:
    data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    items = data["requirements"]
    by_id = {item["id"]: item for item in items}

    related = "; ".join([
        "backend/app/modules/fiscal/application/context_service.py",
        "backend/app/modules/fiscal/presentation/context_schemas.py",
        "backend/app/modules/fiscal/presentation/router.py",
        "backend/app/shared/database/operational_schema.sql",
        "backend/alembic_tenant/versions/0032_fiscal_context_versioning.py",
        "apps/tenant-admin-web/src/components/FiscalPanel.vue",
        "backend/tests/fiscal/test_fiscal_context_versioning.py",
        "backend/tests/migrations/test_fiscal_context_versioning_migration.py",
        "docs/fiscal/FISCAL_CONTEXT_VERSIONING.md",
    ])
    evidence = "; ".join([
        "docs/execution/evidence/fiscal-context-targeted-tests-r000010.log",
        "docs/execution/evidence/backend-final-regression-119.log",
        "docs/execution/evidence/alembic-tenant-0032-upgrade.log",
        "docs/execution/evidence/alembic-tenant-0032-downgrade.log",
    ])
    implementation = (
        "Dimensão persistida no contexto/versão fiscal do tenant, resolvida por vigência e escopo de operação, "
        "com idempotência, concorrência otimista, snapshot SHA-256, auditoria e transactional outbox."
    )
    tests = (
        "Testes fiscais comprovam criação e replay idempotente, publicação imediata e futura, resolução histórica, "
        "bloqueio de sobreposição, autorização, isolamento cross-tenant e congelamento do snapshot no documento; "
        "migration 0032 validada em upgrade/downgrade SQL offline."
    )
    for value in range(1727, 1743):
        item = by_id[f"V8-{value:04d}"]
        item.update({
            "status": "VERIFIED",
            "implementation": implementation,
            "tests": tests,
            "evidence": evidence,
            "related_files": related,
        })

    rtc_related = "; ".join([
        "backend/app/modules/fiscal/presentation/context_schemas.py",
        "backend/app/shared/database/operational_schema.sql",
        "backend/alembic_tenant/versions/0032_fiscal_context_versioning.py",
        "apps/tenant-admin-web/src/components/FiscalPanel.vue",
    ])
    for value in range(1784, 1788):
        by_id[f"V8-{value:04d}"].update({
            "status": "IMPLEMENTED",
            "implementation": "Modo RTC disponível por versão fiscal, persistido por estabelecimento e vigência; não existe flag global eterna.",
            "tests": "Schema, migration, OpenAPI e interface validam o contrato; a regressão exercita o modo simulation_only. Os demais modos ainda requerem cenários tributários completos antes de promoção para VERIFIED.",
            "evidence": "docs/execution/evidence/openapi-fiscal-context-r000010.log; docs/execution/evidence/backend-final-regression-119.log",
            "related_files": rtc_related,
        })

    by_id["V8-3027"].update({
        "status": "TESTING",
        "implementation": "Administração fiscal do tenant implementada para estabelecimentos, versões, vigências, escopos, publicação, resolução, documentos e regras, usando somente APIs reais.",
        "tests": "Contratos de rotas, handlers, ausência de vazamento de marca, estrutura do template e TypeScript do SFC aprovados. Build Vite permanece bloqueado pela ausência local de node_modules, lockfile e vue-tsc.",
        "evidence": "docs/execution/evidence/fiscal-context-targeted-tests-r000010.log; docs/execution/evidence/frontend-fiscal-context-validation-r000010.log; docs/execution/evidence/frontend-build-r000010.log",
        "related_files": "apps/tenant-admin-web/src/App.vue; apps/tenant-admin-web/src/components/FiscalPanel.vue; backend/tests/frontend/test_tenant_admin_vertical_modules.py",
    })
    by_id["V8-3585"].update({
        "status": "TESTING",
        "implementation": "Migrations evolutivas, incluindo 0032, possuem SQL de upgrade/downgrade adjacente e contratos automatizados.",
        "tests": "Migration 0032 renderizada para PostgreSQL em upgrade e downgrade e validada por dois testes; execução em PostgreSQL real ainda não é possível neste host.",
        "evidence": "docs/execution/evidence/alembic-tenant-0032-upgrade.log; docs/execution/evidence/alembic-tenant-0032-downgrade.log; docs/execution/evidence/fiscal-context-targeted-tests-r000010.log",
        "related_files": "backend/alembic_tenant/versions/0032_fiscal_context_versioning.py; backend/tests/migrations/test_fiscal_context_versioning_migration.py",
    })
    by_id["V8-3589"].update({
        "status": "VERIFIED",
        "implementation": "Contexto fiscal versionado, documentos condicionais, IBPT e providers desabilitados sem credenciais são exercitados sem alegação de homologação real.",
        "tests": "Regressão consolidada e testes fiscais direcionados aprovados.",
        "evidence": "docs/execution/evidence/backend-final-regression-119.log; docs/execution/evidence/fiscal-context-targeted-tests-r000010.log",
        "related_files": "backend/app/modules/fiscal/; backend/tests/fiscal/; docs/fiscal/FISCAL_CONTEXT_VERSIONING.md",
    })

    counts = Counter(item["status"] for item in items)
    data["generated_at"] = now()
    data["count"] = len(items)
    data["status_summary"] = dict(sorted(counts.items()))
    JSON_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Matriz persistente de requisitos V8",
        "",
        "Esta matriz foi extraída do contrato integral e deve ser atualizada somente com evidência executável. Estados permitidos: `NOT_STARTED`, `IMPLEMENTING`, `IMPLEMENTED`, `TESTING`, `VERIFIED`, `BLOCKED_EXTERNAL`, `NOT_APPLICABLE`.",
        "",
        f"Atualizada em `{data['generated_at']}` após reconciliação com o workspace físico e regressão consolidada.",
        "",
        "## Resumo de estados",
        "",
        "| Estado | Quantidade |",
        "|---|---:|",
    ]
    lines.extend(f"| {status} | {counts[status]} |" for status in sorted(counts))
    lines.extend([
        "",
        "| ID | Seção de origem | Descrição | Módulo | Dependências | Arquivos relacionados | Status | Implementação | Testes | Evidência | Observações |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ])
    fields = ["id", "section", "description", "module", "dependencies", "related_files", "status", "implementation", "tests", "evidence", "observations"]
    for item in items:
        lines.append("| " + " | ".join(esc(item.get(field)) for field in fields) + " |")
    MD_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps({"count": len(items), "status_summary": data["status_summary"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
