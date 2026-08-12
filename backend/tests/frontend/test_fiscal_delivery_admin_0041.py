from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "apps" / "tenant-admin-web" / "src" / "components" / "FiscalPanel.vue"
OPENAPI = ROOT / "docs" / "api" / "openapi.json"


def test_fiscal_admin_exposes_delivery_retry_rejection_and_render_actions():
    source = APP.read_text(encoding="utf-8")
    for token in (
        "deliveryPolicyForm", "createDeliveryPolicy", "retryFiscalDocument", "renderFiscalDocument", "loadFiscalRejection",
        "/fiscal/delivery-policies", "/rejection", "/render", "Retry", "Renderizar", "Diagnóstico da rejeição",
        "Contingência após", "Retry automático pelo worker conforme countdown versionado",
    ):
        assert token in source, token


def test_openapi_contains_delivery_resilience_contracts():
    spec = json.loads(OPENAPI.read_text(encoding="utf-8"))
    expected = {
        "/api/v1/fiscal/delivery-policies": {"get", "post"},
        "/api/v1/fiscal/delivery-policies/{policy_id}/publish": {"post"},
        "/api/v1/fiscal/documents/{document_id}/rejection": {"get"},
        "/api/v1/fiscal/documents/{document_id}/render": {"post"},
        "/api/v1/fiscal/documents/{document_id}/retry": {"post"},
    }
    for path, methods in expected.items():
        assert path in spec["paths"], path
        assert methods <= set(spec["paths"][path]), (path, methods)
    operation_ids = [
        value.get("operationId")
        for methods in spec["paths"].values()
        for method, value in methods.items()
        if method in {"get", "post", "put", "patch", "delete"}
    ]
    assert len(operation_ids) == len(set(operation_ids))
