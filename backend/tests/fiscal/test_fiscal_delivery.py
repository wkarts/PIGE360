from __future__ import annotations

import base64
from typing import Any

from app.shared.events.dispatcher import event_envelope
from app.worker import handle_event

SIGNING_SECRET = "fiscal-event-secret-" + "x" * 64


class FiscalFakeTransport:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def request_json(self, method: str, url: str, *, headers: dict[str, str], body: Any | None = None, timeout: float = 20.0, retries: int = 2):
        self.calls.append({"method": method, "url": url, "headers": dict(headers), "body": body})
        if url.endswith("/health"):
            return 200, {"status": "ok"}
        if url.endswith("/v1/fiscal/documents"):
            xml = b'<?xml version="1.0" encoding="UTF-8"?><nfeProc><protNFe>LOCAL-HOMOLOG</protNFe></nfeProc>'
            return 201, {
                "state": "authorized",
                "id": "provider-doc-001",
                "event_id": "provider-event-001",
                "access_key": "29260812345678000123550010000001231000001234",
                "protocol": "129260000000001",
                "number": "123",
                "series": "1",
                "xml_base64": base64.b64encode(xml).decode("ascii"),
            }
        if url.endswith("/v1/fiscal/documents/provider-doc-001/cancel"):
            return 200, {"state": "cancelled", "id": "provider-doc-001", "event_id": "provider-cancel-001"}
        raise AssertionError(f"fixture fiscal ausente: {method} {url}")

    def request_form(self, method: str, url: str, *, headers: dict[str, str], form: dict[str, str], timeout: float = 20.0, retries: int = 0):
        raise AssertionError("request_form não esperado")


def _secret(local_env, name: str, value: str = "fiscal-local-token") -> None:
    root = local_env.root / "integration-secrets"
    root.mkdir(parents=True, exist_ok=True)
    (root / name).write_text(value, encoding="utf-8")


def _event(local_env, document_id: str, event_type: str) -> dict:
    router = local_env.client.app.state.data_router
    tid = local_env.alpha_tenant["id"]
    store = router.tenant_store(tid)
    row = store.fetch_one(
        "SELECT * FROM outbox_events WHERE tenant_id=? AND aggregate_id=? AND event_type=? ORDER BY created_at DESC LIMIT 1",
        (tid, document_id, event_type),
    )
    assert row, (document_id, event_type)
    return event_envelope(row, tenant_id=tid, secret=SIGNING_SECRET, plane="tenant")


def test_fiscal_requested_event_authorizes_stores_xml_and_cancels(local_env):
    _secret(local_env, "fiscal-provider")
    connection = local_env.client.post(
        "/api/v1/integration-connections",
        headers=local_env.alpha_headers(),
        json={
            "provider": "SefazNfeProvider",
            "name": "Gateway fiscal homologação",
            "environment": "homologation",
            "capabilities": ["issue", "cancel"],
            "secret_reference": "fiscal-provider",
            "config": {"base_url": "https://fiscal.example.edu.br"},
        },
    )
    assert connection.status_code == 201, connection.text

    profile = local_env.client.post(
        "/api/v1/fiscal/profiles",
        headers=local_env.alpha_headers(),
        json={
            "establishment_name": "Colégio Alpha",
            "cnpj": "12345678000123",
            "tax_regime": "simples_nacional",
            "uf": "BA",
            "environment": "homologation",
            "provider_connection_id": connection.json()["id"],
        },
    )
    assert profile.status_code == 201, profile.text

    requested = local_env.client.post(
        "/api/v1/fiscal/documents",
        headers=local_env.alpha_headers(**{"Idempotency-Key": "fiscal-doc-001"}),
        json={
            "fiscal_profile_id": profile.json()["id"],
            "source_type": "manual",
            "source_id": "sale-local-001",
            "document_type": "NF-e",
            "totals": {"total": "100.00"},
            "payload": {"operation": "sale"},
        },
    )
    assert requested.status_code == 201, requested.text
    document_id = requested.json()["id"]
    assert requested.json()["provider_status"] == "queued"

    router = local_env.client.app.state.data_router
    transport = FiscalFakeTransport()
    consumed = handle_event(
        _event(local_env, document_id, "FiscalDocumentRequested"),
        router=router,
        signing_secret=SIGNING_SECRET,
        transport=transport,
    )
    assert consumed["status"] == "completed"
    store = router.tenant_store(local_env.alpha_tenant["id"])
    document = store.fetch_one("SELECT * FROM fiscal_documents WHERE tenant_id=? AND id=?", (local_env.alpha_tenant["id"], document_id))
    assert document and document["state"] == "authorized"
    assert document["provider_document_id"] == "provider-doc-001"
    assert document["xml_sha256"] and document["xml_storage_key"]
    xml = router.object_storage(local_env.alpha_tenant["id"]).get_bytes(document["xml_storage_key"])
    assert b"nfeProc" in xml
    assert "xml_base64" not in (document["response_json"] or "")
    events = local_env.client.get(f"/api/v1/fiscal/documents/{document_id}/events", headers=local_env.alpha_headers())
    assert events.status_code == 200, events.text
    assert any(item["event_type"] == "authorized" for item in events.json()["items"])

    cancel = local_env.client.post(
        f"/api/v1/fiscal/documents/{document_id}/cancel",
        headers=local_env.alpha_headers(),
        json={"reason": "Operação cancelada em homologação"},
    )
    assert cancel.status_code == 200, cancel.text
    assert cancel.json()["state"] == "cancellation_requested"
    cancelled = handle_event(
        _event(local_env, document_id, "FiscalDocumentCancellationRequested"),
        router=router,
        signing_secret=SIGNING_SECRET,
        transport=transport,
    )
    assert cancelled["status"] == "completed"
    final = store.fetch_one("SELECT * FROM fiscal_documents WHERE tenant_id=? AND id=?", (local_env.alpha_tenant["id"], document_id))
    assert final and final["state"] == "cancelled"


def test_fiscal_event_without_provider_never_fakes_authorization(local_env):
    profile = local_env.client.post(
        "/api/v1/fiscal/profiles",
        headers=local_env.alpha_headers(),
        json={"establishment_name": "Sem provider", "cnpj": "99999999000199", "tax_regime": "normal", "uf": "BA", "environment": "homologation"},
    )
    assert profile.status_code == 201, profile.text
    requested = local_env.client.post(
        "/api/v1/fiscal/documents",
        headers=local_env.alpha_headers(**{"Idempotency-Key": "fiscal-no-provider-001"}),
        json={"fiscal_profile_id": profile.json()["id"], "source_type": "manual", "source_id": "manual-2", "document_type": "NFS-e", "totals": {"total": "50.00"}},
    )
    assert requested.status_code == 201, requested.text
    document_id = requested.json()["id"]
    result = handle_event(
        _event(local_env, document_id, "FiscalDocumentRequested"),
        router=local_env.client.app.state.data_router,
        signing_secret=SIGNING_SECRET,
    )
    assert result["status"] == "completed"
    store = local_env.client.app.state.data_router.tenant_store(local_env.alpha_tenant["id"])
    row = store.fetch_one("SELECT state,provider_status,access_key FROM fiscal_documents WHERE tenant_id=? AND id=?", (local_env.alpha_tenant["id"], document_id))
    assert row == {"state": "awaiting_provider_configuration", "provider_status": "not_configured", "access_key": None}
