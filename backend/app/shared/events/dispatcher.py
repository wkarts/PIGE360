from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Callable, Protocol

from app.shared.domain.ids import iso_now, uuid7
from app.shared.events.records import add_outbox


class EventStore(Protocol):
    def fetch_one(self, sql: str, params: tuple[Any, ...] | list[Any] = ()) -> dict[str, Any] | None: ...
    def fetch_all(self, sql: str, params: tuple[Any, ...] | list[Any] = ()) -> list[dict[str, Any]]: ...
    def execute(self, sql: str, params: tuple[Any, ...] | list[Any] = ()) -> int: ...
    def transaction(self): ...


SendTask = Callable[[dict[str, Any], str], Any]
EventHandler = Callable[[EventStore, dict[str, Any]], dict[str, Any] | None]


@dataclass(frozen=True, slots=True)
class PublishResult:
    published: int
    failed: int
    event_ids: tuple[str, ...]


def sign_tenant_context(payload: dict[str, Any], secret: str) -> dict[str, Any]:
    unsigned = dict(payload)
    canonical = json.dumps(unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    unsigned["signature"] = hmac.new(secret.encode("utf-8"), canonical, hashlib.sha256).hexdigest()
    return unsigned


def queue_for_event(event_type: str) -> str:
    prefixes = (
        (("Teaching", "Lesson", "Curriculum", "Grade"), "pedagogy"),
        (("ClassSession", "Attendance", "StudentMarked", "GuardianAbsence"), "attendance"),
        (("Payment", "Charge", "Financial", "Installment"), "finance"),
        (("Fiscal",), "fiscal"),
        (("Contract",), "contracts"),
        (("Signature", "GovBr", "IcpBrasil"), "signatures"),
        (("Mailbox", "Mail"), "mail"),
        (("Notification", "Notice"), "notifications"),
        (("Document",), "documents"),
        (("Integration", "Webhook"), "integrations"),
        (("TenantApp",), "app-builds"),
    )
    for names, queue in prefixes:
        if event_type.startswith(names):
            return queue
    return "default"


def event_envelope(
    row: dict[str, Any], *, tenant_id: str, secret: str, plane: str = "tenant"
) -> dict[str, Any]:
    try:
        payload = json.loads(row.get("payload_json") or "{}")
    except (TypeError, json.JSONDecodeError):
        payload = {}
    return {
        "event_id": row["id"],
        "event_type": row["event_type"],
        "event_version": int(row.get("event_version") or 1),
        "aggregate_type": row["aggregate_type"],
        "aggregate_id": row["aggregate_id"],
        "payload": payload,
        "correlation_id": row["correlation_id"],
        "created_at": row["created_at"],
        "tenant_context": sign_tenant_context({"tenant_id": tenant_id, "plane": plane}, secret),
    }


def publish_pending_outbox(
    store: EventStore,
    *,
    tenant_id: str | None,
    signing_secret: str,
    send_task: SendTask,
    limit: int = 100,
    plane: str = "tenant",
) -> PublishResult:
    now = iso_now()
    if tenant_id is None:
        rows = store.fetch_all(
            "SELECT * FROM outbox_events WHERE tenant_id IS NULL AND published_at IS NULL "
            "AND (next_attempt_at IS NULL OR next_attempt_at<=?) ORDER BY created_at LIMIT ?",
            (now, limit),
        )
        context_tenant_id = "__platform__"
    else:
        rows = store.fetch_all(
            "SELECT * FROM outbox_events WHERE tenant_id=? AND published_at IS NULL "
            "AND (next_attempt_at IS NULL OR next_attempt_at<=?) ORDER BY created_at LIMIT ?",
            (tenant_id, now, limit),
        )
        context_tenant_id = tenant_id
    published: list[str] = []; failed = 0
    for row in rows:
        envelope = event_envelope(row, tenant_id=context_tenant_id, secret=signing_secret, plane=plane)
        queue = queue_for_event(str(row["event_type"]))
        try:
            send_task(envelope, queue)
        except Exception as exc:
            failed += 1
            attempts = int(row.get("attempts") or 0) + 1
            delay = min(3600, 2 ** min(attempts, 10))
            retry_at = (datetime.now(UTC) + timedelta(seconds=delay)).isoformat().replace("+00:00", "Z")
            store.execute(
                "UPDATE outbox_events SET attempts=?,last_error=?,next_attempt_at=? WHERE id=? AND published_at IS NULL",
                (attempts, f"{type(exc).__name__}: {str(exc)[:1000]}", retry_at, row["id"]),
            )
            continue
        store.execute(
            "UPDATE outbox_events SET published_at=?,attempts=attempts+1,last_error=NULL,next_attempt_at=NULL WHERE id=? AND published_at IS NULL",
            (iso_now(), row["id"]),
        )
        published.append(str(row["id"]))
    return PublishResult(len(published), failed, tuple(published))


def _condition_matches(conditions: dict[str, Any], payload: dict[str, Any]) -> bool:
    for key, expected in conditions.items():
        current: Any = payload
        for part in key.split("."):
            if not isinstance(current, dict) or part not in current:
                return False
            current = current[part]
        if isinstance(expected, dict):
            if "eq" in expected and current != expected["eq"]:
                return False
            if "in" in expected and current not in expected["in"]:
                return False
            if "gte" in expected and current < expected["gte"]:
                return False
            if "lte" in expected and current > expected["lte"]:
                return False
        elif current != expected:
            return False
    return True


def execute_domain_automations(store: EventStore, envelope: dict[str, Any]) -> list[dict[str, Any]]:
    tenant_id = str(envelope["tenant_context"]["tenant_id"])
    event_type = str(envelope["event_type"])
    payload = dict(envelope.get("payload") or {})
    rules = store.fetch_all(
        "SELECT * FROM automation_rules WHERE tenant_id=? AND trigger_type='domain_event' AND trigger_key=? AND state='active' ORDER BY version DESC",
        (tenant_id, event_type),
    )
    executions: list[dict[str, Any]] = []
    for rule in rules:
        try:
            conditions = json.loads(rule.get("conditions_json") or "{}")
            actions = json.loads(rule.get("actions_json") or "[]")
        except json.JSONDecodeError:
            conditions, actions = {}, []
        matched = _condition_matches(conditions if isinstance(conditions, dict) else {}, payload)
        action_results: list[dict[str, Any]] = []
        execution_id = uuid7(); now = iso_now()
        with store.transaction() as conn:
            if matched:
                for index, action in enumerate(actions if isinstance(actions, list) else []):
                    if not isinstance(action, dict):
                        continue
                    kind = str(action.get("type") or "")
                    if kind in {"send_notification", "send_email", "send_whatsapp", "send_push", "notify_manager"}:
                        channel = {
                            "send_email": "email", "send_whatsapp": "whatsapp", "send_push": "push",
                            "notify_manager": str(action.get("channel") or "internal"),
                        }.get(kind, str(action.get("channel") or "internal"))
                        notification_id = uuid7(); idem = f"automation:{execution_id}:{index}"
                        recipient = action.get("recipient_person_id") or payload.get("person_id")
                        body = str(action.get("body") or payload.get("message") or rule["name"])
                        conn.execute(
                            "INSERT INTO notifications(id,tenant_id,recipient_person_id,channel,template_key,subject,body,state,idempotency_key,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                            (notification_id, tenant_id, recipient, channel, action.get("template_key"), action.get("subject"), body, "queued", idem, now),
                        )
                        add_outbox(conn, tenant_id=tenant_id, event_type="NotificationRequested", aggregate_type="notification", aggregate_id=notification_id, payload={"notification_id": notification_id, "channel": channel}, correlation_id=str(envelope.get("correlation_id") or envelope["event_id"]))
                        action_results.append({"type": kind, "id": notification_id, "state": "queued"})
                    elif kind == "create_request":
                        request_id = uuid7(); protocol = f"AUTO-{request_id[-10:].upper()}"
                        conn.execute(
                            "INSERT INTO service_requests(id,tenant_id,protocol,requester_person_id,request_type,subject,description,priority,department,state,version,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            (request_id, tenant_id, protocol, payload.get("person_id"), action.get("request_type", "automation"), action.get("subject", rule["name"]), action.get("description"), action.get("priority", "normal"), action.get("department"), "open", 1, now, now),
                        )
                        add_outbox(conn, tenant_id=tenant_id, event_type="ServiceRequestCreated", aggregate_type="service_request", aggregate_id=request_id, payload={"id": request_id, "protocol": protocol, "source": "automation"}, correlation_id=str(envelope.get("correlation_id") or envelope["event_id"]))
                        action_results.append({"type": kind, "id": request_id, "state": "open"})
                    elif kind in {"provision_mailbox", "suspend_mailbox", "call_webhook", "generate_document", "start_workflow", "create_charge", "create_calendar_event", "create_task"}:
                        deferred_event = {
                            "provision_mailbox": "MailboxProvisionRequested", "suspend_mailbox": "MailboxSuspendRequested",
                            "call_webhook": "IntegrationWebhookRequested", "generate_document": "DocumentGenerationRequested",
                            "start_workflow": "WorkflowStartRequested", "create_charge": "ChargeCreationRequested",
                            "create_calendar_event": "CalendarEventCreationRequested", "create_task": "TaskCreationRequested",
                        }[kind]
                        deferred_id = uuid7()
                        add_outbox(conn, tenant_id=tenant_id, event_type=deferred_event, aggregate_type="automation_action", aggregate_id=deferred_id, payload={"action": action, "source_event_id": envelope["event_id"], "payload": payload}, correlation_id=str(envelope.get("correlation_id") or envelope["event_id"]))
                        action_results.append({"type": kind, "id": deferred_id, "state": "queued"})
                    else:
                        action_results.append({"type": kind or "unknown", "state": "unsupported"})
            state = "completed" if all(item.get("state") != "unsupported" for item in action_results) else "completed_with_unsupported_actions"
            conn.execute(
                "INSERT INTO automation_executions(id,tenant_id,rule_id,event_id,state,dry_run,input_json,result_json,started_at,finished_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (execution_id, tenant_id, rule["id"], envelope["event_id"], state, 0, json.dumps(payload, ensure_ascii=False, sort_keys=True), json.dumps({"matched": matched, "actions": action_results}, ensure_ascii=False, sort_keys=True), now, iso_now()),
            )
        executions.append({"rule_id": rule["id"], "execution_id": execution_id, "matched": matched, "actions": action_results})
    return executions


class DomainEventDispatcher:
    def __init__(self, handlers: dict[str, EventHandler] | None = None, *, run_automations: bool = True):
        self.handlers = handlers or {}
        self.run_automations = run_automations

    def dispatch(self, store: EventStore, envelope: dict[str, Any]) -> dict[str, Any]:
        event_type = str(envelope["event_type"])
        result: dict[str, Any] = {"event_type": event_type, "handler": "observed"}
        handler = self.handlers.get(event_type)
        if handler is not None:
            domain = handler(store, envelope) or {}
            result = {"event_type": event_type, "handler": "executed", "domain": domain}
        automations = execute_domain_automations(store, envelope) if self.run_automations else []
        if automations:
            result["automations"] = automations
        return result


def consume_event(
    store: EventStore,
    *,
    envelope: dict[str, Any],
    consumer: str,
    dispatcher: DomainEventDispatcher,
) -> dict[str, Any]:
    tenant_id = str(envelope["tenant_context"]["tenant_id"])
    event_id = str(envelope["event_id"]); event_type = str(envelope["event_type"]); now = iso_now()
    existing = store.fetch_one(
        "SELECT * FROM inbox_events WHERE tenant_id=? AND event_id=? AND consumer=?",
        (tenant_id, event_id, consumer),
    )
    if existing and existing["state"] == "completed":
        try:
            prior = json.loads(existing.get("result_json") or "{}")
        except json.JSONDecodeError:
            prior = {}
        return {"status": "duplicate", "event_id": event_id, "result": prior}
    if not existing:
        store.execute(
            "INSERT INTO inbox_events(id,tenant_id,event_id,consumer,event_type,state,attempts,result_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(tenant_id,event_id,consumer) DO NOTHING",
            (uuid7(), tenant_id, event_id, consumer, event_type, "processing", 1, "{}", now, now),
        )
    else:
        store.execute(
            "UPDATE inbox_events SET state='processing',attempts=attempts+1,last_error=NULL,updated_at=? WHERE tenant_id=? AND event_id=? AND consumer=?",
            (now, tenant_id, event_id, consumer),
        )
    try:
        result = dispatcher.dispatch(store, envelope)
    except Exception as exc:
        store.execute(
            "UPDATE inbox_events SET state='failed',last_error=?,updated_at=? WHERE tenant_id=? AND event_id=? AND consumer=?",
            (f"{type(exc).__name__}: {str(exc)[:1000]}", iso_now(), tenant_id, event_id, consumer),
        )
        raise
    finished = iso_now()
    store.execute(
        "UPDATE inbox_events SET state='completed',result_json=?,processed_at=?,updated_at=? WHERE tenant_id=? AND event_id=? AND consumer=?",
        (json.dumps(result, ensure_ascii=False, sort_keys=True), finished, finished, tenant_id, event_id, consumer),
    )
    return {"status": "completed", "event_id": event_id, "result": result}
