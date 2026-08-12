#!/usr/bin/env python3
"""Atualiza conservadoramente a matriz V8 com as evidências físicas deste checkpoint."""
from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JSON_PATH = ROOT / "docs/execution/requirements.json"
MD_PATH = ROOT / "docs/execution/REQUIREMENTS_MATRIX.md"
ALLOWED = {"NOT_STARTED", "IMPLEMENTING", "IMPLEMENTED", "TESTING", "VERIFIED", "BLOCKED_EXTERNAL", "NOT_APPLICABLE"}
def latest_final_regression() -> str:
    evidence = ROOT / "docs/execution/evidence"
    candidates: list[tuple[int, Path]] = []
    for status_path in evidence.glob("backend-final-regression-*.status"):
        match = re.fullmatch(r"backend-final-regression-(\d+)\.status", status_path.name)
        if not match or status_path.read_text(encoding="utf-8").strip() != "0":
            continue
        log_path = status_path.with_suffix(".log")
        if log_path.exists():
            candidates.append((int(match.group(1)), log_path))
    if not candidates:
        raise RuntimeError("Nenhuma regressão consolidada aprovada foi encontrada.")
    return max(candidates, key=lambda item: item[0])[1].relative_to(ROOT).as_posix()


FINAL_REGRESSION = latest_final_regression()


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def patch(item: dict, *, status: str, implementation: str, tests: str, evidence: str, related_files: str | None = None) -> None:
    if status not in ALLOWED:
        raise ValueError(status)
    item["status"] = status
    item["implementation"] = implementation
    item["tests"] = tests
    item["evidence"] = evidence
    if related_files is not None:
        item["related_files"] = related_files


def esc(value: object) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", "<br>")


def main() -> int:
    data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    items = data["requirements"]
    by_id = {item["id"]: item for item in items}

    # Corrige a evidência física dos tokens centrais.
    item = by_id["V8-0248"]
    item["evidence"] = "packages/design-tokens/src/tokens.json"
    item["related_files"] = "backend/app/bootstrap/settings.py; packages/design-tokens/src/tokens.json"

    # Catálogo e execução de serviços: categorias genéricas suportadas pelo mesmo agregado.
    service_categories = [f"V8-{value:04d}" for value in range(1556, 1574)]
    for rid in service_categories:
        patch(
            by_id[rid],
            status="IMPLEMENTED",
            implementation="A categoria é representável pelo catálogo tipado de serviços, variações, vigência, recorrência, cobrança e execução; integrações específicas do domínio relacionado continuam avaliadas separadamente.",
            tests="Contrato genérico exercitado pelo cenário vertical de serviços; não equivale à conclusão do módulo especializado citado na categoria.",
            evidence="docs/execution/evidence/services-vertical-test.log",
            related_files="backend/app/modules/services/application/vertical_service.py; backend/app/modules/services/presentation/vertical_schemas.py; backend/app/modules/services/presentation/router.py",
        )

    service_verified = list(range(1574, 1591)) + [1592, 1594, 1595, 1596, 1597, 1598] + list(range(1600, 1608)) + [1610]
    for value in service_verified:
        rid = f"V8-{value:04d}"
        patch(
            by_id[rid],
            status="VERIFIED",
            implementation="Fluxo vertical persistente de serviços com tenant, vigência, recorrência, competência, cobrança, execução, cancelamento/estorno, classificação fiscal, auditoria e outbox.",
            tests="Cenário vertical, replay idempotente, cobrança transacional, execução, cancelamento compensatório e isolamento incluídos na regressão consolidada.",
            evidence=FINAL_REGRESSION,
            related_files="backend/app/modules/services/application/vertical_service.py; backend/app/modules/services/presentation/vertical_schemas.py; backend/app/modules/services/presentation/router.py; backend/tests/services/test_services_vertical.py; backend/alembic_tenant/versions/0030_services_procurement_assets_vertical.py",
        )

    patch(
        by_id["V8-1593"],
        status="IMPLEMENTED",
        implementation="Centro de custo está persistido no serviço, pedido, contas a receber e geração por competência.",
        tests="Cobertura estrutural e regressão dos fluxos financeiros; falta cenário dedicado de rateio por múltiplos centros.",
        evidence=FINAL_REGRESSION,
        related_files="backend/app/shared/database/operational_schema.sql; backend/app/modules/services/application/vertical_service.py",
    )
    patch(
        by_id["V8-1608"],
        status="IMPLEMENTING",
        implementation="A solicitação/evento fiscal de serviço e a classificação para NFS-e são persistidos; emissão real permanece condicionada a provider municipal/nacional configurado.",
        tests="Estados `not_configured` e bloqueio por classificação incompleta são exercitados; não existe homologação real sem credenciais e protocolo.",
        evidence=FINAL_REGRESSION,
        related_files="backend/app/modules/services/application/vertical_service.py; backend/app/modules/fiscal/",
    )

    # Estoque, compras e patrimônio.
    procurement_verified = [1701, 1702, 1704, 1705, 1710, 1712, 1714, 1715, 1716, 1717, 1718, 1719, 1720, 1721, 1722, 1723, 1724, 1725, 1726]
    for value in procurement_verified:
        rid = f"V8-{value:04d}"
        patch(
            by_id[rid],
            status="VERIFIED",
            implementation="Fluxo vertical persistente de compras, recebimento por lote, estoque, inventário, devolução e ciclo patrimonial, com tenant, autorização, idempotência, auditoria e outbox.",
            tests="Cenário integrado cobre fornecedor, cotação, proposta, adjudicação, pedido, recebimento parcial/final, rollback, lote/validade, reserva, inventário, devolução, transferência, empréstimo, manutenção e depreciação.",
            evidence=FINAL_REGRESSION,
            related_files="backend/app/modules/procurement/application/vertical_service.py; backend/app/modules/procurement/presentation/vertical_schemas.py; backend/app/modules/procurement/presentation/router.py; backend/app/modules/inventory/presentation/router.py; backend/app/modules/assets/application/vertical_service.py; backend/app/modules/assets/presentation/router.py; backend/tests/sales/test_procurement_assets_vertical.py; backend/alembic_tenant/versions/0030_services_procurement_assets_vertical.py",
        )

    reorder_evidence = (
        "docs/execution/evidence/inventory-reorder-targeted-tests-r000005.log; "
        f"{FINAL_REGRESSION}; "
        "docs/execution/evidence/alembic-tenant-0031-upgrade.log; "
        "docs/execution/evidence/alembic-tenant-0031-downgrade.log"
    )
    reorder_files = (
        "backend/app/shared/database/operational_schema.sql; "
        "backend/alembic_tenant/versions/0031_inventory_reorder_suggestions.py; "
        "backend/app/modules/procurement/application/vertical_service.py; "
        "backend/app/modules/procurement/presentation/vertical_schemas.py; "
        "backend/app/modules/procurement/presentation/router.py; "
        "apps/tenant-admin-web/src/components/ProcurementPanel.vue; "
        "backend/tests/sales/test_inventory_reorder_suggestions.py; "
        "backend/tests/migrations/test_inventory_reorder_suggestions_migration.py"
    )
    for rid in ("V8-1697", "V8-1713"):
        patch(
            by_id[rid],
            status="VERIFIED",
            implementation="Política persistente de estoque mínimo por produto e depósito, cálculo de estoque disponível/projetado, sugestão automática idempotente e conversão transacional em requisição de compra, com tenant, autorização, concorrência otimista, auditoria e outbox.",
            tests="Cenários exercitam estoque físico e reservado, pedidos aprovados em trânsito, geração e atualização idempotentes, supersessão, descarte, conversão em requisição e isolamento cross-tenant; migration 0031 validada em upgrade/downgrade offline.",
            evidence=reorder_evidence,
            related_files=reorder_files,
        )

    # Administração do tenant: código e testes de contrato passaram, mas build Vite está bloqueado por dependências locais ausentes.
    admin_testing = [3022, 3023, 3024, 3025, 3026, 3027, 3029, 3031, 3032, 3033, 3034, 3035, 3036, 3037, 3039, 3040, 3042, 3043, 3047]
    for value in admin_testing:
        rid = f"V8-{value:04d}"
        patch(
            by_id[rid],
            status="TESTING",
            implementation="Superfície administrativa conectada a endpoints reais, com autorização por perfil, estados de carregamento/erro e ações operacionais.",
            tests="Contratos de fonte e sintaxe Vue aprovados; build Vite não executado porque o workspace não contém node_modules, package-lock nem vue-tsc e o acesso de rede está proibido.",
            evidence="docs/execution/evidence/tenant-admin-vertical-source-tests.log; docs/execution/evidence/tenant-admin-sfc-script-syntax.log; docs/execution/evidence/tenant-admin-build-attempt.log",
            related_files="apps/tenant-admin-web/src/App.vue; apps/tenant-admin-web/src/components/",
        )

    # API e contratos técnicos.
    api_verified = [3300, 3301, 3302, 3303, 3306, 3307, 3308, 3310, 3311, 3312, 3313, 3314, 3315, 3316, 3318] + list(range(3320, 3330))
    for value in api_verified:
        rid = f"V8-{value:04d}"
        evidence = "docs/execution/evidence/openapi-sdk-regeneration.log; docs/execution/evidence/api-sdk-typescript-validation.log" if value in {3300, 3301, 3302, 3318} else FINAL_REGRESSION
        patch(
            by_id[rid],
            status="VERIFIED",
            implementation="Contrato técnico implementado no middleware, schemas, routers e OpenAPI/SDK gerados.",
            tests="Regressão consolidada e validação do OpenAPI/SDK TypeScript aprovadas.",
            evidence=evidence,
            related_files="backend/app/main.py; backend/app/shared/; docs/api/openapi.json; packages/api-sdk/src/generated/",
        )
    for value in [3304, 3305, 3309]:
        rid = f"V8-{value:04d}"
        patch(
            by_id[rid],
            status="IMPLEMENTED",
            implementation="Padrão aplicado nos contratos atuais; a auditoria de uniformidade em todos os endpoints ainda não foi concluída.",
            tests="Exemplos representativos passam na regressão; falta scanner de cobertura global dedicado.",
            evidence=FINAL_REGRESSION,
            related_files="backend/app/modules/; backend/app/shared/presentation/",
        )

    # Validações locais executadas neste ambiente.
    validation_updates = {
        3581: ("TESTING", "Type-check do SDK e sintaxe TypeScript das SFCs aprovados; type-check completo da aplicação aguarda dependências locais.", "docs/execution/evidence/api-sdk-typescript-validation.log; docs/execution/evidence/tenant-admin-sfc-script-syntax.log"),
        3582: ("VERIFIED", "Backend compilado e regressão consolidada aprovada.", FINAL_REGRESSION),
        3583: ("TESTING", "Testes de contrato e sintaxe frontend aprovados; build Vite bloqueado por dependências locais ausentes.", "docs/execution/evidence/tenant-admin-vertical-source-tests.log; docs/execution/evidence/tenant-admin-sfc-script-syntax.log; docs/execution/evidence/tenant-admin-build-attempt.log"),
        3585: ("TESTING", "Migrations 0030 e 0031 validadas em SQL offline, upgrade/downgrade adjacente e testes de contrato; falta execução em PostgreSQL real neste host.", "docs/execution/evidence/alembic-0030-contract-tests.log; docs/execution/evidence/alembic-tenant-0030-upgrade.log; docs/execution/evidence/alembic-tenant-0030-downgrade.log; docs/execution/evidence/inventory-reorder-targeted-tests-r000005.log; docs/execution/evidence/alembic-tenant-0031-upgrade.log; docs/execution/evidence/alembic-tenant-0031-downgrade.log"),
        3586: ("VERIFIED", "Isolamento de tenant exercitado por bancos, hosts, tokens, dados e branding separados.", FINAL_REGRESSION),
        3587: ("VERIFIED", "Testes de autenticação, host, replay, assinatura e fronteiras de tenant aprovados.", FINAL_REGRESSION),
        3588: ("VERIFIED", "Ciclo contratual e providers condicionais exercitados.", FINAL_REGRESSION),
        3589: ("VERIFIED", "Orquestração fiscal, catálogos, IBPT e estados condicionais exercitados sem simular homologação real.", FINAL_REGRESSION),
        3590: ("VERIFIED", "Acervo oficial importado, checksums, manifests, tokens e isolamento de marca validados.", "docs/execution/evidence/branding-regression.log"),
        3591: ("VERIFIED", "Contrato visual executado em 40 telas e 132 screenshots sem vazamento entre tenants.", "docs/execution/evidence/visual-contract-after-branding.log"),
        3592: ("VERIFIED", "Planejamento, versões, aprovação, agenda e execução exercitados.", FINAL_REGRESSION),
        3593: ("VERIFIED", "Sessões, chamada, justificativa, correção, reabertura e risco exercitados.", FINAL_REGRESSION),
        3594: ("TESTING", "Fluxos offline representativos são testados, mas o engine compartilhado e todos os clientes nativos ainda não estão concluídos.", FINAL_REGRESSION),
        3595: ("VERIFIED", "OpenAPI regenerado sem operationIds duplicados.", "docs/execution/evidence/openapi-sdk-regeneration.log"),
        3596: ("VERIFIED", "SDK TypeScript regenerado e validado em modo estrito.", "docs/execution/evidence/api-sdk-typescript-validation.log"),
        3599: ("TESTING", "Há cenários E2E operacionais, porém o conjunto integral do contrato V8 ainda não foi concluído.", FINAL_REGRESSION),
    }
    for value, (status, implementation, evidence) in validation_updates.items():
        patch(
            by_id[f"V8-{value:04d}"],
            status=status,
            implementation=implementation,
            tests="Resultado persistido no arquivo de evidência indicado.",
            evidence=evidence,
            related_files="backend/tests/; apps/tenant-admin-web/; docs/api/; packages/api-sdk/",
        )

    # Branding, referências e App Factory: promove apenas o que possui evidência local executável.
    branding_updates = {
        3803: ("VERIFIED", "Tokens oficiais centralizados em CSS, SCSS, JSON e preset compartilhado."),
        3804: ("VERIFIED", "Preview e validação de contraste WCAG exercitados."),
        3805: ("VERIFIED", "Marca global restrita às superfícies globais verificadas; tenants usam marca própria."),
        3806: ("TESTING", "Branding do tenant aplicado às aplicações existentes; ainda faltam superfícies obrigatórias não construídas."),
        3807: ("VERIFIED", "Testes cross-tenant e regressão visual não detectaram vazamento de ativos."),
        3808: ("VERIFIED", "Catálogo visual contém 40 telas e 132 screenshots reais."),
        3809: ("VERIFIED", "Regressão visual executada e aprovada."),
        3810: ("VERIFIED", "Manifestos PWA/Tauri referenciam ícones reais e válidos."),
        3811: ("IMPLEMENTED", "Identificadores estão persistidos nos manifestos; estabilidade após primeira distribuição ainda requer build/release nativo."),
        3812: ("VERIFIED", "Resource packs e derivados foram gerados sem alterar os originais."),
        3814: ("IMPLEMENTED", "Assinatura está condicionada à presença de segredos nos contratos e workflows; não executada neste host."),
    }
    for value, (status, implementation) in branding_updates.items():
        evidence = "docs/execution/evidence/visual-contract-after-branding.log" if value in {3805, 3806, 3807, 3808, 3809} else "docs/execution/evidence/branding-regression.log"
        patch(
            by_id[f"V8-{value:04d}"],
            status=status,
            implementation=implementation,
            tests="Importação oficial, manifests, contraste, isolamento e contrato visual exercitados conforme aplicável.",
            evidence=evidence,
            related_files="scripts/branding/import_official_assets.py; packages/design-tokens/; packages/tenant-branding/; apps/; docs/design/",
        )

    # Atualiza timestamps e resumo.
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
