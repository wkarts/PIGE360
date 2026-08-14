from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "apps" / "tenant-admin-web" / "src"
OPENAPI = ROOT / "docs" / "api" / "openapi.json"


def _text(relative: str) -> str:
    return (APP / relative).read_text(encoding="utf-8")


def test_tenant_admin_registers_services_procurement_and_assets_surfaces() -> None:
    app = _text("App.vue")
    for component, area, label in (
        ("ServicesPanel", "services", "Serviços"),
        ("ProcurementPanel", "procurement", "Compras"),
        ("AssetsPanel", "assets", "Patrimônio"),
        ("FiscalPanel", "fiscal", "Fiscal"),
    ):
        assert f'import {component} from "./components/{component}.vue"' in app
        assert re.search(rf'\[\s*"{re.escape(area)}"\s*,\s*"{re.escape(label)}"', app)
        assert re.search(rf"active\s*===\s*['\"]{re.escape(area)}['\"]", app)
        assert re.search(rf"<{re.escape(component)}\s+:api=\"api\"", app)


def test_vertical_panels_only_call_routes_present_in_current_openapi() -> None:
    paths = json.loads(OPENAPI.read_text(encoding="utf-8"))["paths"]
    contracts = {
        "components/ServicesPanel.vue": {
            "/api/v1/service-catalogs",
            "/api/v1/services",
            "/api/v1/service-subscriptions",
            "/api/v1/service-orders",
            "/api/v1/service-executions",
            "/api/v1/service-fiscal-events",
            "/api/v1/services-dashboard",
            "/api/v1/services/{service_id}/variants",
            "/api/v1/services/{service_id}/price-tables",
            "/api/v1/services/{service_id}/fiscal-profiles",
            "/api/v1/services/{service_id}/billing-rules",
            "/api/v1/service-subscriptions/{subscription_id}/competencies",
            "/api/v1/service-orders/{order_id}/executions",
            "/api/v1/service-orders/{order_id}/receipts",
            "/api/v1/service-orders/{order_id}/receipt-payments",
            "/api/v1/service-receipts/{receipt_id}",
            "/api/v1/service-receipts/{receipt_id}/document",
            "/api/v1/service-receipts/{receipt_id}/void",
        },
        "components/ProcurementPanel.vue": {
            "/api/v1/products",
            "/api/v1/suppliers",
            "/api/v1/inventory/product-variants",
            "/api/v1/inventory/product-barcodes",
            "/api/v1/procurement/requisitions",
            "/api/v1/procurement/quotations",
            "/api/v1/procurement/orders",
            "/api/v1/inventory/lots",
            "/api/v1/inventory/reservations",
            "/api/v1/inventory/counts",
            "/api/v1/inventory/counts/{count_id}/complete",
            "/api/v1/inventory/reorder-policies",
            "/api/v1/inventory/reorder-policies/{policy_id}",
            "/api/v1/inventory/purchase-suggestions",
            "/api/v1/inventory/purchase-suggestions/generate",
            "/api/v1/inventory/purchase-suggestions/{suggestion_id}/convert",
            "/api/v1/inventory/purchase-suggestions/{suggestion_id}/dismiss",
        },
        "components/AssetsPanel.vue": {
            "/api/v1/asset-locations",
            "/api/v1/assets",
            "/api/v1/assets/{asset_id}",
            "/api/v1/assets/{asset_id}/transfers",
            "/api/v1/assets/{asset_id}/maintenances",
            "/api/v1/assets/{asset_id}/loans",
            "/api/v1/assets/{asset_id}/depreciations",
            "/api/v1/asset-maintenances/{maintenance_id}/start",
            "/api/v1/asset-maintenances/{maintenance_id}/complete",
            "/api/v1/asset-loans/{loan_id}/return",
        },
        "components/FiscalPanel.vue": {
            "/api/v1/fiscal/contexts",
            "/api/v1/fiscal/contexts/{context_id}",
            "/api/v1/fiscal/contexts/{context_id}/versions",
            "/api/v1/fiscal/contexts/{context_id}/versions/{version_id}/publish",
            "/api/v1/fiscal/contexts/resolve",
            "/api/v1/fiscal/documents",
            "/api/v1/fiscal/certificates",
            "/api/v1/fiscal/providers",
            "/api/v1/fiscal/providers/{configuration_id}",
            "/api/v1/fiscal/providers/{configuration_id}/health",
            "/api/v1/fiscal/documents/{document_id}",
            "/api/v1/fiscal/documents/{document_id}/query",
            "/api/v1/fiscal/documents/{document_id}/substitute",
            "/api/v1/fiscal/documents/{document_id}/events",
            "/api/v1/fiscal/inutilizations",
            "/api/v1/fiscal/document-schemas",
            "/api/v1/fiscal/document-schemas/{schema_id}/publish",
            "/api/v1/fiscal/routing-policies",
            "/api/v1/fiscal/routing-policies/{policy_id}/publish",
            "/api/v1/fiscal/document-assemblies",
            "/api/v1/fiscal/document-assemblies/{assembly_id}",
            "/api/v1/fiscal/emission-trigger-runs",
            "/api/v1/fiscal/emission-trigger-runs/evaluate",
            "/api/v1/fiscal/rules",
            "/api/v1/fiscal/catalogs",
            "/api/v1/fiscal/catalogs/{catalog_id}",
            "/api/v1/fiscal/catalogs/{catalog_id}/versions",
            "/api/v1/fiscal/catalogs/{catalog_id}/versions/{version_id}/publish",
            "/api/v1/fiscal/catalogs/{catalog_id}/resolve/{code}",
            "/api/v1/fiscal/classification-rules",
            "/api/v1/fiscal/classification-rules/{rule_id}",
            "/api/v1/fiscal/classification-rules/{rule_id}/publish",
            "/api/v1/fiscal/readiness",
            "/api/v1/fiscal/tax-rule-sets",
            "/api/v1/fiscal/tax-rule-sets/{rule_set_id}",
            "/api/v1/fiscal/tax-rule-sets/{rule_set_id}/versions",
            "/api/v1/fiscal/tax-rule-sets/{rule_set_id}/versions/{version_id}/publish",
            "/api/v1/fiscal/tax-calculations/simulate",
            "/api/v1/fiscal/tax-calculations/{calculation_id}",
            "/api/v1/fiscal/catalog-sources",
            "/api/v1/fiscal/catalogs/{catalog_id}/sources",
            "/api/v1/fiscal/catalog-imports",
            "/api/v1/fiscal/catalogs/{catalog_id}/imports",
            "/api/v1/fiscal/catalog-imports/{run_id}",
            "/api/v1/fiscal/catalog-imports/{run_id}/publish",
            "/api/v1/fiscal/catalogs/{catalog_id}/versions/{version_id}/rollback",
            "/api/v1/fiscal/catalog-governance/health",
            "/api/v1/fiscal/catalog-quarantine",
            "/api/v1/fiscal/catalog-quarantine/{quarantine_id}/resolve",
            "/api/v1/integration-connections",
            "/api/v1/references/catalog",
        },
    }
    for relative, expected_paths in contracts.items():
        source = _text(relative)
        assert "TODO" not in source
        assert "módulo em construção" not in source.lower()
        assert "implementar depois" not in source.lower()
        for path in expected_paths:
            assert path in paths, f"Rota ausente do OpenAPI: {path}"
            static_prefix = path.removeprefix("/api/v1").split("/{", 1)[0]
            assert static_prefix in source, f"Painel {relative} não referencia {path}"


def test_every_declared_vertical_action_has_an_executable_handler() -> None:
    required_handlers = {
        "components/ServicesPanel.vue": {
            "createCatalog", "createService", "showService", "updateServiceStatus", "createVariant",
            "createPrice", "createFiscalProfile", "publishFiscal", "createBillingRule", "createSubscription",
            "subscriptionAction", "generateCompetence", "createOrder", "orderAction", "showOrder",
            "issueReceipt", "downloadReceipt", "voidReceipt", "scheduleExecution", "executionAction", "load",
        },
        "components/ProcurementPanel.vue": {
            "createSupplier", "createProduct", "toggleSupplier", "createVariant", "createBarcode", "createRequisition",
            "showRequisition", "requisitionAction", "createQuotation", "showQuotation", "submitProposal",
            "awardQuotation", "createOrder", "showOrder", "approveOrder", "receiveOrder", "returnOrderItem",
            "createReservation", "reservationAction", "createCount", "completeCount",
            "clearPolicyEditor", "editReorderPolicy", "saveReorderPolicy", "toggleReorderPolicy",
            "generatePurchaseSuggestions", "selectSuggestion", "convertSelectedSuggestion",
            "dismissSelectedSuggestion", "load",
        },
        "components/AssetsPanel.vue": {
            "createLocation", "createAsset", "showAsset", "transferAsset", "createMaintenance",
            "startMaintenance", "completeMaintenance", "createLoan", "returnLoan", "calculateDepreciation", "load",
        },
        "components/FiscalPanel.vue": {
            "createContext", "showContext", "updateContextStatus", "addScope", "removeScope",
            "createVersion", "publishVersion", "resolveCurrent", "createCatalog", "createCatalogVersion",
            "createClassification", "calculateReadiness", "createTaxRuleSet", "createTaxRuleVersion",
            "simulateTaxCalculation", "addTaxComponent", "removeTaxComponent",
            "createCatalogSource", "selectCatalogImportFile", "importCatalogFile",
            "publishCatalogImport", "rollbackCatalogImport", "resolveCatalogQuarantine",
            "createFiscalCertificate", "createFiscalProvider", "checkFiscalProvider", "queryFiscalDocument",
            "cancelFiscalDocument", "substituteFiscalDocument", "requestCorrectionEvent", "createFiscalInutilization",
            "createDocumentSchema", "publishDocumentSchema", "createRoutingPolicy", "assembleFiscalDocument", "evaluateEmissionTrigger", "load",
        },
    }
    for relative, required in required_handlers.items():
        source = _text(relative)
        declared = set(re.findall(r"(?:async\s+)?function\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", source))
        assert required <= declared, f"Handlers ausentes em {relative}: {sorted(required - declared)}"
        for handler in required - {"load"}:
            assert re.search(rf"@(?:click|submit\.prevent|change)=\"[^\"]*\b{re.escape(handler)}\b", source), (
                f"Handler {handler} não está ligado a uma ação de interface em {relative}"
            )


def test_school_sales_catalog_categories_are_aligned_between_ui_and_openapi() -> None:
    source = _text("components/ProcurementPanel.vue")
    spec = json.loads(OPENAPI.read_text(encoding="utf-8"))
    expected = {
        "general",
        "school_uniform",
        "textbook",
        "handout",
        "learning_module",
        "educational_material",
        "school_kit",
        "event_ticket",
        "event",
    }
    category_schema = spec["components"]["schemas"]["ProductInput"]["properties"]["school_catalog_category"]
    contract_categories = set(category_schema["anyOf"][0]["enum"])
    query = next(
        item for item in spec["paths"]["/api/v1/products"]["get"]["parameters"]
        if item["name"] == "school_catalog_category"
    )
    assert contract_categories == expected
    assert set(query["schema"]["anyOf"][0]["enum"]) == expected
    for category in expected:
        assert f'value="{category}"' in source
    assert "createProduct" in source


def test_fiscal_routing_surface_exposes_financial_cancel_policy_without_fake_payment_deletion() -> None:
    source = _text("components/FiscalPanel.vue")
    assert "financial_cancel_mode" in source
    assert "cancel_unpaid_charge" in source
    assert "require_financial_contract" in source
    assert "tax_regime_filter" in source
    assert "municipality_filter" in source
    assert "nunca apaga pagamento confirmado" in source


def test_tenant_surface_does_not_render_global_product_wordmark() -> None:
    visible_sources = [
        _text("App.vue"),
        _text("components/ServicesPanel.vue"),
        _text("components/ProcurementPanel.vue"),
        _text("components/AssetsPanel.vue"),
        _text("components/FiscalPanel.vue"),
    ]
    for source in visible_sources:
        template = source.split("<template>", 1)[1] if "<template>" in source else source
        assert ">PIGE360<" not in template
        assert "PIGE360 —" not in template
