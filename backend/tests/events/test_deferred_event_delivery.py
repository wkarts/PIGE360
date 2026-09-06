from __future__ import annotations

import pytest

from app.shared.domain.ids import uuid7
from app.shared.events.dispatcher import (
    DEFERRED_EVENT_TYPES,
    DeferredEventHandlerUnavailable,
    DomainEventDispatcher,
    consume_event,
    sign_tenant_context,
)
from app.worker import handle_event


SIGNING_SECRET = "deferred-event-test-secret-" + "x" * 64


def _envelope(tenant_id: str, event_type: str, *, event_id: str | None = None, payload: dict | None = None) -> dict:
    target_id = event_id or uuid7()
    return {
        "event_id": target_id,
        "event_type": event_type,
        "event_version": 1,
        "aggregate_type": "automation_action",
        "aggregate_id": uuid7(),
        "payload": payload or {},
        "correlation_id": uuid7(),
        "created_at": "2026-09-04T00:00:00Z",
        "tenant_context": {"tenant_id": tenant_id, "plane": "tenant"},
    }


@pytest.mark.parametrize("event_type", sorted(DEFERRED_EVENT_TYPES))
def test_deferred_event_without_handler_is_failed_not_observed(local_env, event_type: str):
    tenant_id = local_env.alpha_tenant["id"]
    store = local_env.client.app.state.data_router.tenant_store(tenant_id)
    envelope = _envelope(tenant_id, event_type)
    with pytest.raises(DeferredEventHandlerUnavailable):
        consume_event(
            store,
            envelope=envelope,
            consumer="deferred-test",
            dispatcher=DomainEventDispatcher(run_automations=False),
        )
    inbox = store.fetch_one(
        "SELECT state,attempts,result_json,last_error FROM inbox_events WHERE tenant_id=? AND event_id=? AND consumer=?",
        (tenant_id, envelope["event_id"], "deferred-test"),
    )
    assert inbox and inbox["state"] == "failed" and inbox["attempts"] == 1
    assert "observed" not in inbox["result_json"]
    assert event_type in inbox["last_error"]


def test_deferred_event_moves_to_application_dead_letter_after_retry_budget(local_env):
    tenant_id = local_env.beta_tenant["id"]
    store = local_env.client.app.state.data_router.tenant_store(tenant_id)
    envelope = _envelope(tenant_id, "IntegrationWebhookRequested")
    dispatcher = DomainEventDispatcher(run_automations=False)
    for _ in range(7):
        with pytest.raises(DeferredEventHandlerUnavailable):
            consume_event(store, envelope=envelope, consumer="dead-letter-test", dispatcher=dispatcher)
    result = consume_event(store, envelope=envelope, consumer="dead-letter-test", dispatcher=dispatcher)
    assert result["status"] == "dead_lettered"
    assert result["result"] == {
        "event_type": "IntegrationWebhookRequested",
        "handler": "dead_lettered",
        "reason": "required_handler_unavailable",
        "attempts": 8,
    }
    inbox = store.fetch_one(
        "SELECT state,attempts,processed_at FROM inbox_events WHERE tenant_id=? AND event_id=? AND consumer=?",
        (tenant_id, envelope["event_id"], "dead-letter-test"),
    )
    assert inbox and inbox["state"] == "dead_lettered" and inbox["attempts"] == 8 and inbox["processed_at"]

    recovered = consume_event(
        store,
        envelope=envelope,
        consumer="dead-letter-test",
        dispatcher=DomainEventDispatcher(
            handlers={"IntegrationWebhookRequested": lambda _store, _envelope: {"state": "submitted"}},
            run_automations=False,
        ),
    )
    assert recovered["status"] == "completed"
    assert recovered["result"]["domain"] == {"state": "submitted"}
    assert store.fetch_one(
        "SELECT state,attempts FROM inbox_events WHERE tenant_id=? AND event_id=? AND consumer=?",
        (tenant_id, envelope["event_id"], "dead-letter-test"),
    ) == {"state": "completed", "attempts": 9}


def test_non_deferred_event_keeps_observed_compatibility(local_env):
    tenant_id = local_env.alpha_tenant["id"]
    store = local_env.client.app.state.data_router.tenant_store(tenant_id)
    result = consume_event(
        store,
        envelope=_envelope(tenant_id, "FutureInformationalEvent"),
        consumer="observed-test",
        dispatcher=DomainEventDispatcher(run_automations=False),
    )
    assert result["status"] == "completed"
    assert result["result"]["handler"] == "observed"


def test_workflow_start_deferred_event_executes_local_domain_handler_idempotently(local_env):
    definition = local_env.client.post(
        "/api/v1/workflows/definitions",
        headers=local_env.alpha_headers(),
        json={
            "code": "automation.student.onboarding",
            "name": "Onboarding automatizado",
            "aggregate_type": "student",
            "steps": [
                {
                    "key": "review",
                    "name": "Revisar onboarding",
                    "type": "task",
                    "assignee_roles": ["tenant_owner"],
                    "approve_to": "completed",
                    "reject_to": "cancelled",
                }
            ],
        },
    )
    assert definition.status_code == 201, definition.text
    published = local_env.client.post(
        f"/api/v1/workflows/definitions/{definition.json()['id']}/publish",
        headers=local_env.alpha_headers(),
        json={"expected_version": 1, "reason": "Fluxo aprovado para automação"},
    )
    assert published.status_code == 200, published.text

    tenant_id = local_env.alpha_tenant["id"]
    event_id = uuid7()
    envelope = _envelope(
        tenant_id,
        "WorkflowStartRequested",
        event_id=event_id,
        payload={
            "action": {
                "type": "start_workflow",
                "definition_code": "automation.student.onboarding",
                "aggregate_type": "student",
                "aggregate_id": "student-test-001",
                "context": {"origin": "test"},
            },
            "source_event_id": uuid7(),
            "payload": {},
        },
    )
    envelope["tenant_context"] = sign_tenant_context(
        {"tenant_id": tenant_id, "plane": "tenant"}, SIGNING_SECRET
    )
    router = local_env.client.app.state.data_router
    first = handle_event(envelope, router=router, signing_secret=SIGNING_SECRET)
    second = handle_event(envelope, router=router, signing_secret=SIGNING_SECRET)
    assert first["status"] == "completed"
    assert first["result"]["handler"] == "executed"
    assert first["result"]["domain"]["state"] == "active"
    assert second["status"] == "duplicate"
    store = router.tenant_store(tenant_id)
    assert store.scalar(
        "SELECT COUNT(*) FROM workflow_instances WHERE tenant_id=? AND aggregate_type=? AND aggregate_id=?",
        (tenant_id, "student", "student-test-001"),
    ) == 1
