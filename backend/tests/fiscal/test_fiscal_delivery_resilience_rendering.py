from __future__ import annotations

import hashlib
from datetime import date
from typing import Any

from app.modules.fiscal.application.document_delivery_service import retry_plan
from app.shared.events.dispatcher import event_envelope
from app.shared.integrations.providers import IntegrationError
from app.worker import handle_event

SIGNING_SECRET = "fiscal-delivery-resilience-" + "k" * 64


class RetryableFiscalTransport:
    def request_json(self, method: str, url: str, *, headers: dict[str, str], body: Any | None = None, timeout: float = 20.0, retries: int = 0):
        if method == "POST" and url.endswith("/v1/fiscal/documents"):
            raise IntegrationError("FISCAL_UPSTREAM_TIMEOUT", "Timeout fiscal da fixture.", retryable=True)
        if method == "GET" and url.endswith("/health"):
            return 200, {"status": "ok"}
        raise AssertionError(f"fixture não implementada: {method} {url}")

    def request_form(self, *args, **kwargs):
        raise AssertionError("form não esperado")

    def request_bytes(self, *args, **kwargs):
        raise AssertionError("bytes não esperado")


class RejectedFiscalTransport:
    def request_json(self, method: str, url: str, *, headers: dict[str, str], body: Any | None = None, timeout: float = 20.0, retries: int = 0):
        if method == "POST" and url.endswith("/v1/fiscal/documents"):
            return 200, {"state": "rejected", "code": "539", "message": "Rejeição fiscal fixture: duplicidade controlada."}
        if method == "GET" and url.endswith("/health"):
            return 200, {"status": "ok"}
        raise AssertionError(f"fixture não implementada: {method} {url}")

    def request_form(self, *args, **kwargs):
        raise AssertionError("form não esperado")

    def request_bytes(self, *args, **kwargs):
        raise AssertionError("bytes não esperado")


def _secret(local_env, name: str, value: str = "fixture-secret") -> None:
    root = local_env.root / "integration-secrets"
    root.mkdir(parents=True, exist_ok=True)
    (root / name).write_text(value, encoding="utf-8")


def _provider(local_env) -> dict[str, Any]:
    _secret(local_env, "fiscal-delivery-token")
    response = local_env.client.post(
        "/api/v1/fiscal/providers",
        headers=local_env.alpha_headers(**{"Idempotency-Key": "delivery-provider-001"}),
        json={
            "provider_code": "ThirdPartyFiscalProvider",
            "display_name": "Provider fiscal fixture",
            "document_type": "NF-e",
            "environment": "homologation",
            "endpoint_url": "https://fiscal-delivery.fixture.invalid",
            "secret_ref": "fiscal-delivery-token",
            "capabilities": ["issue", "query", "cancel", "health"],
            "enabled": True,
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "configured"
    return response.json()


def _profile(local_env, provider_id: str) -> dict[str, Any]:
    response = local_env.client.post(
        "/api/v1/fiscal/profiles",
        headers=local_env.alpha_headers(),
        json={
            "establishment_name": "Colégio Alpha",
            "cnpj": "12345678000123",
            "tax_regime": "simples_nacional",
            "uf": "BA",
            "environment": "homologation",
            "provider_connection_id": provider_id,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _policy(local_env, *, auto_retry: bool = False, max_attempts: int = 2, contingency_after_attempts: int | None = 1) -> dict[str, Any]:
    response = local_env.client.post(
        "/api/v1/fiscal/delivery-policies",
        headers=local_env.alpha_headers(**{"Idempotency-Key": f"delivery-policy-{auto_retry}-{max_attempts}"}),
        json={
            "code": "nfe-thirdparty-homolog",
            "name": "Entrega NF-e fixture",
            "document_type": "NF-e",
            "provider_code": "ThirdPartyFiscalProvider",
            "environment": "homologation",
            "valid_from": "2026-01-01",
            "priority": 10,
            "max_attempts": max_attempts,
            "base_delay_seconds": 30,
            "max_delay_seconds": 120,
            "backoff_multiplier": "2",
            "jitter_seconds": 0,
            "auto_retry": auto_retry,
            "contingency_after_attempts": contingency_after_attempts,
            "contingency_mode": "offline" if contingency_after_attempts else None,
        },
    )
    assert response.status_code == 201, response.text
    row = response.json()
    published = local_env.client.post(
        f"/api/v1/fiscal/delivery-policies/{row['id']}/publish",
        headers=local_env.alpha_headers(),
        json={"expected_version": row["version"], "reason": "Política fiscal validada pela fixture local."},
    )
    assert published.status_code == 200, published.text
    return published.json()


def _document(local_env, profile_id: str, suffix: str, document_type: str = "NF-e") -> str:
    response = local_env.client.post(
        "/api/v1/fiscal/documents",
        headers=local_env.alpha_headers(**{"Idempotency-Key": f"delivery-document-{suffix}"}),
        json={
            "fiscal_profile_id": profile_id,
            "source_type": "manual",
            "source_id": f"delivery-source-{suffix}",
            "document_type": document_type,
            "totals": {"total": "321.45"},
            "payload": {"operation": "sale", "fixture": suffix},
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _event(local_env, document_id: str) -> dict[str, Any]:
    tenant_id = local_env.alpha_tenant["id"]
    store = local_env.client.app.state.data_router.tenant_store(tenant_id)
    row = store.fetch_one(
        "SELECT * FROM outbox_events WHERE tenant_id=? AND aggregate_id=? AND event_type='FiscalDocumentRequested' ORDER BY created_at DESC,id DESC LIMIT 1",
        (tenant_id, document_id),
    )
    assert row
    return event_envelope(row, tenant_id=tenant_id, secret=SIGNING_SECRET, plane="tenant")


def test_retry_policy_rejection_contingency_and_manual_reprocess(local_env):
    provider = _provider(local_env)
    profile = _profile(local_env, provider["id"])
    policy = _policy(local_env, auto_retry=False, max_attempts=2, contingency_after_attempts=1)
    document_id = _document(local_env, profile["id"], "retry")
    router = local_env.client.app.state.data_router

    first = handle_event(_event(local_env, document_id), router=router, signing_secret=SIGNING_SECRET, transport=RetryableFiscalTransport())
    assert first["status"] == "completed"
    assert first["result"]["domain"]["state"] == "retry_pending"

    store = router.tenant_store(local_env.alpha_tenant["id"])
    row = store.fetch_one("SELECT * FROM fiscal_documents WHERE tenant_id=? AND id=?", (local_env.alpha_tenant["id"], document_id))
    assert row["state"] == "requested"
    assert row["retry_count"] == 1
    assert row["delivery_policy_id"] == policy["id"]
    assert row["next_retry_at"]
    assert row["contingency_mode"] == "offline"

    rejection = local_env.client.get(f"/api/v1/fiscal/documents/{document_id}/rejection", headers=local_env.alpha_headers())
    assert rejection.status_code == 200, rejection.text
    current = rejection.json()["rejection"]
    assert current["retryable"] is True and current["state"] == "retry_scheduled"
    assert current["category"] == "transport" and current["delivery_policy_id"] == policy["id"]

    retry = local_env.client.post(
        f"/api/v1/fiscal/documents/{document_id}/retry",
        headers=local_env.alpha_headers(),
        json={"reason": "Reprocessamento manual após análise da falha temporária."},
    )
    assert retry.status_code == 200, retry.text
    assert retry.json()["delivery_policy_id"] == policy["id"]

    second = handle_event(_event(local_env, document_id), router=router, signing_secret=SIGNING_SECRET, transport=RetryableFiscalTransport())
    assert second["status"] == "completed"
    assert second["result"]["domain"]["state"] == "rejected"
    row = store.fetch_one("SELECT state,retry_count,next_retry_at FROM fiscal_documents WHERE tenant_id=? AND id=?", (local_env.alpha_tenant["id"], document_id))
    assert row == {"state": "rejected", "retry_count": 2, "next_retry_at": None}
    assert store.scalar("SELECT COUNT(*) FROM fiscal_document_rejections WHERE tenant_id=? AND fiscal_document_id=?", (local_env.alpha_tenant["id"], document_id)) == 2

    blocked = local_env.client.post(
        f"/api/v1/fiscal/documents/{document_id}/retry",
        headers=local_env.alpha_headers(),
        json={"reason": "Tentativa sem override após esgotamento."},
    )
    assert blocked.status_code == 409 and blocked.json()["code"] == "FISCAL_RETRY_LIMIT_REACHED"
    forced = local_env.client.post(
        f"/api/v1/fiscal/documents/{document_id}/retry",
        headers=local_env.alpha_headers(),
        json={"reason": "Override operacional auditado após revisão humana.", "force": True},
    )
    assert forced.status_code == 200, forced.text
    assert store.scalar("SELECT COUNT(*) FROM outbox_events WHERE tenant_id=? AND aggregate_id=? AND event_type='FiscalDocumentContingencyActivated'", (local_env.alpha_tenant["id"], document_id)) == 1


def test_provider_rejection_and_deterministic_local_danfe(local_env):
    provider = _provider(local_env)
    profile = _profile(local_env, provider["id"])
    _policy(local_env, auto_retry=False, max_attempts=3, contingency_after_attempts=None)
    document_id = _document(local_env, profile["id"], "rejected")
    router = local_env.client.app.state.data_router

    result = handle_event(_event(local_env, document_id), router=router, signing_secret=SIGNING_SECRET, transport=RejectedFiscalTransport())
    assert result["status"] == "completed" and result["result"]["domain"]["state"] == "rejected"
    rejection = local_env.client.get(f"/api/v1/fiscal/documents/{document_id}/rejection", headers=local_env.alpha_headers())
    assert rejection.status_code == 200
    current = rejection.json()["rejection"]
    assert current["category"] == "provider_rejection" and current["error_code"] == "539" and current["retryable"] is False

    first = local_env.client.post(f"/api/v1/fiscal/documents/{document_id}/render", headers=local_env.alpha_headers(), json={})
    second = local_env.client.post(f"/api/v1/fiscal/documents/{document_id}/render", headers=local_env.alpha_headers(), json={})
    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["artifact_type"] == "danfe_local"
    assert first.json()["sha256"] == second.json()["sha256"] and second.json()["idempotent"] is True
    pdf = router.object_storage(local_env.alpha_tenant["id"]).get_bytes(first.json()["storage_key"])
    assert pdf.startswith(b"%PDF-1.4") and pdf.endswith(b"%%EOF\n")
    assert hashlib.sha256(pdf).hexdigest() == first.json()["sha256"]
    assert b"PIGE360" not in pdf  # superfície white-label não recebe marca global automaticamente.

    cross = local_env.client.get(f"/api/v1/fiscal/documents/{document_id}/rejection", headers=local_env.beta_headers())
    assert cross.status_code == 404


def test_retry_plan_is_deterministic_and_exponential():
    policy = {
        "id": "policy-1", "max_attempts": 5, "base_delay_seconds": 10, "max_delay_seconds": 100,
        "backoff_multiplier": "2", "jitter_seconds": 0, "auto_retry": True,
        "contingency_after_attempts": 3, "contingency_mode": "svc",
    }
    p1 = retry_plan(policy, document_id="doc-1", attempt_number=1)
    p2 = retry_plan(policy, document_id="doc-1", attempt_number=2)
    p3 = retry_plan(policy, document_id="doc-1", attempt_number=3)
    p5 = retry_plan(policy, document_id="doc-1", attempt_number=5)
    assert (p1["delay_seconds"], p2["delay_seconds"], p3["delay_seconds"]) == (10, 20, 40)
    assert p3["contingency_mode"] == "svc"
    assert p5["limit_reached"] is True and p5["next_retry_at"] is None


def test_all_local_artifact_types_support_authenticated_download_and_hash_validation(local_env):
    provider = _provider(local_env)
    profile = _profile(local_env, provider["id"])
    router = local_env.client.app.state.data_router
    downloaded: list[tuple[str, str, str]] = []

    for document_type, artifact_type in (("NF-e", "danfe_local"), ("NFC-e", "danfce_local"), ("NFS-e", "danfse_local")):
        document_id = _document(local_env, profile["id"], f"download-{document_type}", document_type)
        rendered = local_env.client.post(f"/api/v1/fiscal/documents/{document_id}/render", headers=local_env.alpha_headers(), json={})
        assert rendered.status_code == 200, rendered.text
        artifact_id = rendered.json()["id"]
        listed = local_env.client.get(f"/api/v1/fiscal/documents/{document_id}/artifacts", headers=local_env.alpha_headers())
        assert listed.status_code == 200, listed.text
        assert listed.json()["items"][0]["artifact_type"] == artifact_type
        assert listed.json()["items"][0]["available"] is True

        response = local_env.client.get(f"/api/v1/fiscal/documents/{document_id}/artifacts/{artifact_id}/download", headers=local_env.alpha_headers())
        assert response.status_code == 200, response.text
        digest = hashlib.sha256(response.content).hexdigest()
        assert response.headers["x-artifact-sha256"] == digest == rendered.json()["sha256"]
        assert response.headers["x-artifact-bytes"] == str(len(response.content))
        assert artifact_type in response.headers["content-disposition"]
        downloaded.append((document_id, artifact_id, rendered.json()["storage_key"]))

    document_id, artifact_id, storage_key = downloaded[0]
    storage = router.object_storage(local_env.alpha_tenant["id"])
    storage.local_path(storage_key).write_bytes(b"artefato adulterado")
    invalid = local_env.client.get(f"/api/v1/fiscal/documents/{document_id}/artifacts/{artifact_id}/download", headers=local_env.alpha_headers())
    assert invalid.status_code == 409
    assert invalid.json()["code"] == "FISCAL_ARTIFACT_INTEGRITY_FAILED"


def test_fiscal_artifact_download_does_not_cross_tenants(local_env):
    provider = _provider(local_env)
    profile = _profile(local_env, provider["id"])
    document_id = _document(local_env, profile["id"], "cross-tenant")
    rendered = local_env.client.post(f"/api/v1/fiscal/documents/{document_id}/render", headers=local_env.alpha_headers(), json={})
    assert rendered.status_code == 200, rendered.text
    response = local_env.client.get(f"/api/v1/fiscal/documents/{document_id}/artifacts/{rendered.json()['id']}/download", headers=local_env.beta_headers())
    assert response.status_code == 404
