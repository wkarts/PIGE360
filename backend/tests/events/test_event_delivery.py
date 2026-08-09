from __future__ import annotations

import json

import pytest

from app.shared.domain.ids import iso_now, uuid7
from app.shared.events.dispatcher import DomainEventDispatcher, consume_event, publish_pending_outbox
from app.shared.events.records import add_outbox
from app.worker import handle_event


SIGNING_SECRET = "event-test-secret-" + "x" * 64


def test_outbox_inbox_automation_and_duplicate_replay(local_env):
    router = local_env.client.app.state.data_router
    tenant_id = local_env.alpha_tenant["id"]
    store = router.tenant_store(tenant_id)
    now = iso_now()
    rule_id = uuid7()
    with store.transaction() as conn:
        conn.execute(
            """INSERT INTO automation_rules(
                   id,tenant_id,name,trigger_type,trigger_key,conditions_json,actions_json,state,version,created_at,updated_at
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (
                rule_id,
                tenant_id,
                "Boas-vindas operacional",
                "domain_event",
                "PersonRegistered",
                json.dumps({"source": {"eq": "test"}}),
                json.dumps(
                    [
                        {"type": "send_notification", "body": "Cadastro recebido"},
                        {"type": "create_request", "request_type": "onboarding", "subject": "Conferir cadastro"},
                    ]
                ),
                "active",
                1,
                now,
                now,
            ),
        )
        event_id = add_outbox(
            conn,
            tenant_id=tenant_id,
            event_type="PersonRegistered",
            aggregate_type="person",
            aggregate_id=uuid7(),
            payload={"source": "test"},
            correlation_id=uuid7(),
        )

    delivered: list[tuple[dict, str]] = []
    result = publish_pending_outbox(
        store,
        tenant_id=tenant_id,
        signing_secret=SIGNING_SECRET,
        send_task=lambda envelope, queue: delivered.append((envelope, queue)),
    )
    assert result.published == 1
    assert result.failed == 0
    assert delivered[0][0]["event_id"] == event_id
    assert delivered[0][0]["tenant_context"]["plane"] == "tenant"

    first = handle_event(delivered[0][0], router=router, signing_secret=SIGNING_SECRET)
    assert first["status"] == "completed"
    execution = store.fetch_one("SELECT * FROM automation_executions WHERE tenant_id=? AND rule_id=?", (tenant_id, rule_id))
    assert execution and execution["state"] == "completed"
    notification = store.fetch_one("SELECT * FROM notifications WHERE tenant_id=?", (tenant_id,))
    assert notification and notification["state"] == "queued"
    notification_event = store.fetch_one("SELECT * FROM outbox_events WHERE tenant_id=? AND aggregate_id=? AND event_type='NotificationRequested'", (tenant_id, notification["id"]))
    assert notification_event
    from app.shared.events.dispatcher import event_envelope
    delivered_notification = event_envelope(notification_event, tenant_id=tenant_id, secret=SIGNING_SECRET, plane="tenant")
    notification_result = handle_event(delivered_notification, router=router, signing_secret=SIGNING_SECRET)
    assert notification_result["status"] == "completed"
    notification = store.fetch_one("SELECT * FROM notifications WHERE tenant_id=? AND id=?", (tenant_id, notification["id"]))
    assert notification and notification["state"] == "sent" and notification["provider_message_id"].startswith("internal:")
    request = store.fetch_one("SELECT * FROM service_requests WHERE tenant_id=?", (tenant_id,))
    assert request and request["protocol"].startswith("AUTO-") and request["request_type"] == "onboarding"

    second = handle_event(delivered[0][0], router=router, signing_secret=SIGNING_SECRET)
    assert second["status"] == "duplicate"
    assert store.scalar("SELECT COUNT(*) AS total FROM automation_executions WHERE tenant_id=? AND rule_id=?", (tenant_id, rule_id)) == 1
    assert store.scalar("SELECT COUNT(*) AS total FROM notifications WHERE tenant_id=?", (tenant_id,)) == 1
    assert store.scalar("SELECT COUNT(*) AS total FROM service_requests WHERE tenant_id=?", (tenant_id,)) == 1


def test_outbox_failure_keeps_event_pending_with_backoff(local_env):
    router = local_env.client.app.state.data_router
    tenant_id = local_env.beta_tenant["id"]
    store = router.tenant_store(tenant_id)
    with store.transaction() as conn:
        event_id = add_outbox(
            conn,
            tenant_id=tenant_id,
            event_type="DocumentGenerated",
            aggregate_type="document",
            aggregate_id=uuid7(),
            payload={"document_id": uuid7()},
            correlation_id=uuid7(),
        )

    def fail(_envelope, _queue):
        raise ConnectionError("broker indisponível")

    result = publish_pending_outbox(
        store,
        tenant_id=tenant_id,
        signing_secret=SIGNING_SECRET,
        send_task=fail,
    )
    assert result.published == 0 and result.failed == 1
    row = store.fetch_one("SELECT * FROM outbox_events WHERE id=?", (event_id,))
    assert row and row["published_at"] is None
    assert row["attempts"] == 1
    assert "ConnectionError" in row["last_error"]
    assert row["next_attempt_at"] is not None


def test_control_plane_event_uses_its_own_consumer_inbox(local_env):
    router = local_env.client.app.state.data_router
    tenant_id = local_env.alpha_tenant["id"]
    with router.control.transaction() as conn:
        event_id = add_outbox(
            conn,
            tenant_id=tenant_id,
            event_type="TenantBrandingPublished",
            aggregate_type="brand_kit",
            aggregate_id=uuid7(),
            payload={"tenant_id": tenant_id},
            correlation_id=uuid7(),
        )

    delivered: list[dict] = []
    result = publish_pending_outbox(
        router.control,
        tenant_id=tenant_id,
        signing_secret=SIGNING_SECRET,
        send_task=lambda envelope, queue: delivered.append(envelope),
        plane="platform",
    )
    assert result.published >= 1
    target = next(item for item in delivered if item["event_id"] == event_id)
    assert target["tenant_context"]["plane"] == "platform"
    consumed = handle_event(target, router=router, signing_secret=SIGNING_SECRET)
    assert consumed["status"] == "completed"
    inbox = router.control.fetch_one(
        "SELECT * FROM inbox_events WHERE tenant_id=? AND event_id=? AND consumer=?",
        (tenant_id, event_id, "pige360-domain-dispatcher-v1"),
    )
    assert inbox and inbox["state"] == "completed"


def test_signed_context_rejects_tenant_tampering(local_env):
    router = local_env.client.app.state.data_router
    tenant_id = local_env.alpha_tenant["id"]
    store = router.tenant_store(tenant_id)
    with store.transaction() as conn:
        add_outbox(
            conn,
            tenant_id=tenant_id,
            event_type="NoticePublished",
            aggregate_type="notice",
            aggregate_id=uuid7(),
            payload={},
            correlation_id=uuid7(),
        )
    delivered: list[dict] = []
    publish_pending_outbox(
        store,
        tenant_id=tenant_id,
        signing_secret=SIGNING_SECRET,
        send_task=lambda envelope, queue: delivered.append(envelope),
    )
    envelope = delivered[0]
    envelope["tenant_context"]["tenant_id"] = local_env.beta_tenant["id"]
    with pytest.raises(ValueError, match="contexto de tenant inválido"):
        handle_event(envelope, router=router, signing_secret=SIGNING_SECRET)


def test_operational_event_retry_clears_backoff_without_replaying_completed(local_env):
    router = local_env.client.app.state.data_router
    tenant_id = local_env.beta_tenant["id"]
    store = router.tenant_store(tenant_id)
    with store.transaction() as conn:
        event_id = add_outbox(
            conn,
            tenant_id=tenant_id,
            event_type="IntegrationWebhookRequested",
            aggregate_type="integration",
            aggregate_id=uuid7(),
            payload={},
            correlation_id=uuid7(),
        )
    publish_pending_outbox(
        store,
        tenant_id=tenant_id,
        signing_secret=SIGNING_SECRET,
        send_task=lambda envelope, queue: (_ for _ in ()).throw(ConnectionError("broker down")),
    )
    failed = local_env.client.get(
        "/api/v1/operations/events/outbox",
        headers=local_env.beta_headers(),
        params={"state": "failed"},
    )
    assert failed.status_code == 200, failed.text
    assert any(item["id"] == event_id for item in failed.json()["items"])
    retry = local_env.client.post(
        f"/api/v1/operations/events/{event_id}/retry",
        headers=local_env.beta_headers(),
        json={"reason": "Broker restaurado após manutenção"},
    )
    assert retry.status_code == 200, retry.text
    row = store.fetch_one("SELECT published_at,last_error,next_attempt_at FROM outbox_events WHERE tenant_id=? AND id=?", (tenant_id, event_id))
    assert row == {"published_at": None, "last_error": None, "next_attempt_at": None}
