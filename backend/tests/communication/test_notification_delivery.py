from __future__ import annotations

import json
from typing import Any

from app.shared.domain.ids import iso_now, uuid7
from app.shared.events.dispatcher import event_envelope
from app.shared.events.records import add_outbox
from app.worker import handle_event

SIGNING_SECRET = "notification-event-secret-" + "x" * 64


class CommunicationFakeTransport:
    def __init__(self) -> None:
        self.emails: list[dict[str, Any]] = []
        self.http_calls: list[dict[str, Any]] = []

    def smtp_health(self, _config: dict[str, Any]):
        return True, {"smtp_code": 250, "fixture": True}

    def send_email(self, message: dict[str, Any]):
        self.emails.append(dict(message))
        return {"message_id": f"smtp-local-{len(self.emails)}"}

    def request_json(self, method: str, url: str, *, headers: dict[str, str], body: Any | None = None, timeout: float = 20.0, retries: int = 2):
        self.http_calls.append({"method": method, "url": url, "headers": dict(headers), "body": body})
        if "/message/sendText/" in url:
            return 201, {"key": {"id": f"wamid-local-{len(self.http_calls)}"}, "status": "PENDING"}
        if url.endswith("/instance/fetchInstances"):
            return 200, [{"instance": {"instanceName": "school"}}]
        raise AssertionError(f"fixture de comunicação ausente: {method} {url}")


def _secret(local_env, name: str, value: str = "local-provider-secret") -> None:
    root = local_env.root / "integration-secrets"
    root.mkdir(parents=True, exist_ok=True)
    (root / name).write_text(value, encoding="utf-8")


def _connection(local_env, *, provider: str, capabilities: list[str], secret_reference: str, config: dict[str, Any]) -> dict[str, Any]:
    response = local_env.client.post(
        "/api/v1/integration-connections",
        headers=local_env.alpha_headers(),
        json={
            "provider": provider,
            "name": f"Fixture {provider}",
            "environment": "homologation",
            "capabilities": capabilities,
            "secret_reference": secret_reference,
            "config": config,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _person(store, tenant_id: str, *, email: str, phone: str) -> str:
    person_id = uuid7(); now = iso_now()
    with store.transaction() as conn:
        conn.execute(
            "INSERT INTO people(id,tenant_id,full_name,email,phone,state,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
            (person_id, tenant_id, "Destinatário Fixture", email, phone, "active", now, now),
        )
    return person_id


def _notification_event(store, tenant_id: str, *, person_id: str, channel: str, body: str) -> tuple[str, dict[str, Any]]:
    notification_id = uuid7(); now = iso_now()
    with store.transaction() as conn:
        conn.execute(
            "INSERT INTO notifications(id,tenant_id,recipient_person_id,channel,subject,body,state,idempotency_key,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (notification_id, tenant_id, person_id, channel, "Aviso PIGE360", body, "queued", f"notif:{notification_id}", now),
        )
        event_id = add_outbox(
            conn,
            tenant_id=tenant_id,
            event_type="NotificationRequested",
            aggregate_type="notification",
            aggregate_id=notification_id,
            payload={"notification_id": notification_id},
            correlation_id=uuid7(),
        )
    row = store.fetch_one("SELECT * FROM outbox_events WHERE id=?", (event_id,))
    assert row
    return notification_id, event_envelope(row, tenant_id=tenant_id, secret=SIGNING_SECRET, plane="tenant")


def test_email_and_whatsapp_notifications_are_delivered_without_remote_io(local_env):
    router = local_env.client.app.state.data_router
    tenant_id = local_env.alpha_tenant["id"]
    store = router.tenant_store(tenant_id)
    fake = CommunicationFakeTransport()

    _secret(local_env, "smtp-secret", "smtp-password-local")
    _secret(local_env, "evolution-secret", "evolution-token-local")
    _connection(
        local_env,
        provider="SmtpEmailProvider",
        capabilities=["send_email"],
        secret_reference="smtp-secret",
        config={
            "host": "smtp.example.edu.br",
            "port": 587,
            "username": "mailer@example.edu.br",
            "from_email": "noreply@example.edu.br",
            "from_name": "Colégio Alpha",
            "tls_mode": "starttls",
        },
    )
    _connection(
        local_env,
        provider="evolution",
        capabilities=["send_text"],
        secret_reference="evolution-secret",
        config={"base_url": "https://whatsapp.example.edu.br", "instance": "school"},
    )
    person_id = _person(store, tenant_id, email="responsavel@example.edu.br", phone="+55 71 99999-0001")

    email_id, email_event = _notification_event(store, tenant_id, person_id=person_id, channel="email", body="Mensagem por e-mail")
    email_result = handle_event(email_event, router=router, signing_secret=SIGNING_SECRET, transport=fake)
    assert email_result["status"] == "completed"
    email_row = store.fetch_one("SELECT state,provider_message_id,attempts FROM notifications WHERE tenant_id=? AND id=?", (tenant_id, email_id))
    assert email_row == {"state": "sent", "provider_message_id": "smtp-local-1", "attempts": 1}
    assert fake.emails == [{
        "from": "noreply@example.edu.br",
        "to": "responsavel@example.edu.br",
        "subject": "Aviso PIGE360",
        "text": "Mensagem por e-mail",
        "html": None,
    }]
    assert "smtp-password-local" not in json.dumps(fake.emails, ensure_ascii=False)

    whatsapp_id, whatsapp_event = _notification_event(store, tenant_id, person_id=person_id, channel="whatsapp", body="Mensagem por WhatsApp")
    whatsapp_result = handle_event(whatsapp_event, router=router, signing_secret=SIGNING_SECRET, transport=fake)
    assert whatsapp_result["status"] == "completed"
    wa_row = store.fetch_one("SELECT state,provider_message_id,attempts FROM notifications WHERE tenant_id=? AND id=?", (tenant_id, whatsapp_id))
    assert wa_row and wa_row["state"] == "sent" and wa_row["provider_message_id"].startswith("wamid-local-") and wa_row["attempts"] == 1
    assert fake.http_calls[-1]["body"]["number"] == "5571999990001"
    assert fake.http_calls[-1]["body"]["text"] == "Mensagem por WhatsApp"


def test_notification_replay_is_inbox_idempotent(local_env):
    router = local_env.client.app.state.data_router
    tenant_id = local_env.alpha_tenant["id"]
    store = router.tenant_store(tenant_id)
    fake = CommunicationFakeTransport()
    _secret(local_env, "smtp-replay")
    _connection(
        local_env,
        provider="smtp",
        capabilities=["send_email"],
        secret_reference="smtp-replay",
        config={"host": "smtp.example.edu.br", "from_email": "noreply@example.edu.br"},
    )
    person_id = _person(store, tenant_id, email="destino@example.edu.br", phone="5571999990002")
    notification_id, envelope = _notification_event(store, tenant_id, person_id=person_id, channel="email", body="Entrega única")

    first = handle_event(envelope, router=router, signing_secret=SIGNING_SECRET, transport=fake)
    second = handle_event(envelope, router=router, signing_secret=SIGNING_SECRET, transport=fake)
    assert first["status"] == "completed"
    assert second["status"] == "duplicate"
    assert len(fake.emails) == 1
    row = store.fetch_one("SELECT state,attempts FROM notifications WHERE tenant_id=? AND id=?", (tenant_id, notification_id))
    assert row == {"state": "sent", "attempts": 1}
