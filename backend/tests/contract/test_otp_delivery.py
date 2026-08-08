from __future__ import annotations

import json
import re
from typing import Any

from app.shared.events.dispatcher import event_envelope
from app.worker import handle_event

SIGNING_SECRET = "otp-delivery-secret-" + "x" * 64


class OtpFakeTransport:
    def __init__(self) -> None:
        self.emails: list[dict[str, Any]] = []

    def smtp_health(self, _config: dict[str, Any]):
        return True, {"smtp_code": 250}

    def send_email(self, message: dict[str, Any]):
        self.emails.append(dict(message))
        return {"message_id": f"otp-smtp-{len(self.emails)}"}


def _secret(local_env, name: str, value: str = "otp-smtp-password") -> None:
    root = local_env.root / "integration-secrets"
    root.mkdir(parents=True, exist_ok=True)
    (root / name).write_text(value, encoding="utf-8")


def _smtp_connection(local_env) -> None:
    _secret(local_env, "otp-smtp")
    response = local_env.client.post(
        "/api/v1/integration-connections",
        headers=local_env.alpha_headers(),
        json={
            "provider": "SmtpEmailProvider",
            "name": "SMTP OTP local",
            "environment": "homologation",
            "capabilities": ["send_email"],
            "secret_reference": "otp-smtp",
            "config": {"host": "smtp.example.edu.br", "from_email": "assinaturas@example.edu.br", "from_name": "Colégio Alpha"},
        },
    )
    assert response.status_code == 201, response.text


def _envelope_for_owner(local_env) -> dict[str, Any]:
    template = local_env.client.post(
        "/api/v1/contract-templates", headers=local_env.alpha_headers(),
        json={"contract_type": "educational_services", "name": "OTP Delivery Fixture"},
    )
    assert template.status_code == 201, template.text
    version = local_env.client.post(
        f"/api/v1/contract-templates/{template.json()['id']}/versions", headers=local_env.alpha_headers(),
        json={"body_text": "Contrato {{contract.number}}", "variables": ["contract.number"], "rules": {}},
    )
    assert version.status_code == 201, version.text
    assert local_env.client.post(f"/api/v1/contract-templates/{template.json()['id']}/publish", headers=local_env.alpha_headers()).status_code == 200
    contract = local_env.client.post(
        "/api/v1/contracts", headers=local_env.alpha_headers(),
        json={"contract_type": "educational_services", "number": "OTP-DELIVERY-001"},
    )
    assert contract.status_code == 201, contract.text
    generated = local_env.client.post(
        f"/api/v1/contracts/{contract.json()['id']}/generate", headers=local_env.alpha_headers(),
        json={"expected_version": contract.json()["version"], "template_version_id": version.json()["id"], "variables": {"contract": {"number": "OTP-DELIVERY-001"}}, "source_references": {}},
    )
    assert generated.status_code == 200, generated.text
    approved = local_env.client.post(
        f"/api/v1/contracts/{contract.json()['id']}/approve", headers=local_env.alpha_headers(),
        json={"expected_version": generated.json()["version"], "reason": "Aprovado para OTP"},
    )
    assert approved.status_code == 200, approved.text
    envelope = local_env.client.post(
        f"/api/v1/contracts/{contract.json()['id']}/send-for-signature", headers=local_env.alpha_headers(),
        json={
            "expected_version": approved.json()["version"],
            "signing_order": "sequential",
            "signers": [{
                "user_id": local_env.alpha_tenant["owner"]["id"],
                "name": "Responsável OTP",
                "email": "owner@alpha.example.com",
                "role": "financial_responsible",
                "required": True,
                "order": 1,
            }],
        },
    )
    assert envelope.status_code == 200, envelope.text
    return envelope.json()


def test_signature_otp_is_delivered_once_without_persisting_plain_code(local_env):
    _smtp_connection(local_env)
    envelope = _envelope_for_owner(local_env)
    otp = local_env.client.post(
        f"/api/v1/signature-envelopes/{envelope['id']}/otp",
        headers=local_env.alpha_headers(),
        json={"channel": "email"},
    )
    assert otp.status_code == 200, otp.text
    test_code = otp.json()["test_code"]
    challenge_id = otp.json()["challenge_id"]

    router = local_env.client.app.state.data_router
    tenant_id = local_env.alpha_tenant["id"]
    store = router.tenant_store(tenant_id)
    event = store.fetch_one(
        "SELECT * FROM outbox_events WHERE tenant_id=? AND event_type='SignatureOtpDeliveryRequested' AND aggregate_id=? ORDER BY created_at DESC LIMIT 1",
        (tenant_id, envelope["id"]),
    )
    assert event
    assert test_code not in str(event.get("payload_json") or "")
    challenge_before = store.fetch_one("SELECT * FROM signature_otp_challenges WHERE tenant_id=? AND id=?", (tenant_id, challenge_id))
    assert challenge_before
    assert test_code not in json.dumps(challenge_before, ensure_ascii=False, default=str)
    assert challenge_before["delivery_state"] == "queued"

    fake = OtpFakeTransport()
    signed_event = event_envelope(event, tenant_id=tenant_id, secret=SIGNING_SECRET, plane="tenant")
    first = handle_event(signed_event, router=router, signing_secret=SIGNING_SECRET, transport=fake)
    second = handle_event(signed_event, router=router, signing_secret=SIGNING_SECRET, transport=fake)
    assert first["status"] == "completed"
    assert second["status"] == "duplicate"
    assert len(fake.emails) == 1
    message = fake.emails[0]
    assert message["to"] == "owner@alpha.example.com"
    assert re.search(rf"\b{re.escape(test_code)}\b", message["text"])
    assert "otp-smtp-password" not in json.dumps(message, ensure_ascii=False)

    challenge_after = store.fetch_one("SELECT * FROM signature_otp_challenges WHERE tenant_id=? AND id=?", (tenant_id, challenge_id))
    assert challenge_after
    assert challenge_after["delivery_state"] == "sent"
    assert challenge_after["delivery_provider"] == "EmailProvider"
    assert challenge_after["delivery_message_id"] == "otp-smtp-1"
    assert challenge_after["delivered_at"] is not None
    assert test_code not in json.dumps(challenge_after, ensure_ascii=False, default=str)

    signed = local_env.client.post(
        f"/api/v1/signature-envelopes/{envelope['id']}/sign",
        headers=local_env.alpha_headers(),
        json={
            "consent": True,
            "document_sha256": envelope["document_sha256"],
            "method": "simple_electronic",
            "otp_challenge_id": challenge_id,
            "otp_code": test_code,
        },
    )
    assert signed.status_code == 200, signed.text
    assert signed.json()["state"] == "signed"
