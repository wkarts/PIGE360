"""Workers Celery do PIGE360.

Pipeline de produção:

    transação de domínio -> outbox_events -> publisher -> RabbitMQ
    -> process_event -> inbox_events -> handler/automações idempotentes

O módulo mantém a importação opcional do Celery para permitir testes offline do
núcleo. Em produção, ``requirements.production.lock`` instala Celery/RabbitMQ/Redis.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import date
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote

from app.bootstrap.config import Settings
from app.modules.fiscal.application.ibpt import UFS, queue_ibpt_sync
from app.modules.fiscal.application.transparency_service import resolve_ibpt_profile
from app.modules.fiscal.application.document_delivery_service import FiscalRetryScheduled
from app.shared.database.router import DataRouter
from app.shared.events.dispatcher import (
    DomainEventDispatcher,
    consume_event,
    publish_pending_outbox,
)
from app.shared.events.handlers import build_domain_event_handlers
from app.shared.domain.ids import iso_now, uuid7
from app.shared.events.records import add_outbox

try:
    from celery import Celery
except ImportError:  # pragma: no cover - ambiente offline sem dependência opcional
    Celery = None  # type: ignore[assignment,misc]


def _secret(env_name: str, file_env_name: str) -> str:
    direct = os.getenv(env_name, "")
    if direct:
        return direct
    file_name = os.getenv(file_env_name, "")
    return Path(file_name).read_text(encoding="utf-8").strip() if file_name and Path(file_name).is_file() else ""


def _authenticated_url(base: str, password: str, *, username: str | None = None) -> str:
    if not password:
        return base
    if base.startswith("redis://"):
        return base.replace("redis://", f"redis://:{quote(password, safe='')}@", 1)
    if base.startswith("amqp://") and username:
        marker = "amqp://"
        rest = base[len(marker):]
        if "@" in rest:
            rest = rest.split("@", 1)[1]
        return f"{marker}{quote(username, safe='')}:{quote(password, safe='')}@{rest}"
    return base


def verify_tenant_context(context: dict[str, Any], secret: str) -> bool:
    """Valida contexto assinado e impede troca de tenant/plane no broker."""
    signature = str(context.get("signature", ""))
    payload = {k: v for k, v in context.items() if k != "signature"}
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    expected = hmac.new(secret.encode("utf-8"), canonical, hashlib.sha256).hexdigest()
    return bool(signature) and bool(secret) and hmac.compare_digest(signature, expected)


_router: DataRouter | None = None


def get_data_router() -> DataRouter:
    """Inicializa um DataRouter por processo do worker, com pools reutilizados."""
    global _router
    if _router is None:
        router = DataRouter(Settings.from_env())
        router.initialize()
        _router = router
    return _router


def handle_event(
    envelope: dict[str, Any],
    *,
    router: DataRouter,
    signing_secret: str,
    consumer: str = "pige360-domain-dispatcher-v1",
    transport: Any | None = None,
) -> dict[str, Any]:
    """Consome um envelope já entregue pelo broker usando inbox idempotente."""
    context = envelope.get("tenant_context")
    if not isinstance(context, dict) or not verify_tenant_context(context, signing_secret):
        raise ValueError("contexto de tenant inválido")
    tenant_id = str(context.get("tenant_id") or "")
    plane = str(context.get("plane") or "")
    if plane == "tenant":
        if not tenant_id or tenant_id == "__platform__":
            raise ValueError("tenant_id ausente no evento do Tenant Plane")
        store = router.tenant_store(tenant_id)
        dispatcher = DomainEventDispatcher(
            handlers=build_domain_event_handlers(router, tenant_id=tenant_id, transport=transport),
            run_automations=True,
        )
    elif plane == "platform":
        # Eventos globais usam o sentinel somente para a chave do consumer inbox.
        store = router.control
        dispatcher = DomainEventDispatcher(run_automations=False)
    else:
        raise ValueError("plane inválido no contexto assinado")
    return consume_event(store, envelope=envelope, consumer=consumer, dispatcher=dispatcher)


def publish_all_pending(
    *,
    router: DataRouter,
    signing_secret: str,
    send_task: Callable[[dict[str, Any], str], Any],
    limit_per_scope: int = 100,
) -> dict[str, Any]:
    """Publica outboxes do Control Plane e de todos os tenants ativos.

    Um tenant indisponível não impede os demais; o erro fica no resumo operacional
    e o evento permanece pendente para a próxima execução.
    """
    summary: dict[str, Any] = {"published": 0, "failed": 0, "scopes": [], "errors": []}

    # Control Plane: eventos podem estar vinculados a um tenant (branding/apps) ou
    # ser realmente globais (tenant_id NULL).
    control_tenants = router.control.fetch_all(
        "SELECT DISTINCT tenant_id FROM outbox_events WHERE published_at IS NULL AND tenant_id IS NOT NULL"
    )
    scopes: list[str | None] = [str(row["tenant_id"]) for row in control_tenants if row.get("tenant_id")]
    if router.control.fetch_one("SELECT id FROM outbox_events WHERE published_at IS NULL AND tenant_id IS NULL LIMIT 1"):
        scopes.append(None)
    for tenant_id in scopes:
        try:
            result = publish_pending_outbox(
                router.control,
                tenant_id=tenant_id,
                signing_secret=signing_secret,
                send_task=send_task,
                limit=limit_per_scope,
                plane="platform",
            )
            summary["published"] += result.published
            summary["failed"] += result.failed
            summary["scopes"].append({"plane": "platform", "tenant_id": tenant_id, "published": result.published, "failed": result.failed})
        except Exception as exc:  # isolamento operacional por escopo
            summary["errors"].append({"plane": "platform", "tenant_id": tenant_id, "error": f"{type(exc).__name__}: {str(exc)[:500]}"})

    tenants = router.control.fetch_all("SELECT id FROM platform_tenants WHERE status='active' ORDER BY id")
    for row in tenants:
        tenant_id = str(row["id"])
        try:
            store = router.tenant_store(tenant_id)
            result = publish_pending_outbox(
                store,
                tenant_id=tenant_id,
                signing_secret=signing_secret,
                send_task=send_task,
                limit=limit_per_scope,
                plane="tenant",
            )
            summary["published"] += result.published
            summary["failed"] += result.failed
            if result.published or result.failed:
                summary["scopes"].append({"plane": "tenant", "tenant_id": tenant_id, "published": result.published, "failed": result.failed})
        except Exception as exc:
            summary["errors"].append({"plane": "tenant", "tenant_id": tenant_id, "error": f"{type(exc).__name__}: {str(exc)[:500]}"})
    return summary


def queue_due_notifications(*, router: DataRouter) -> dict[str, Any]:
    """Promove notificações agendadas vencidas para o transactional outbox.

    A transição ``scheduled -> queued`` ocorre na mesma transação da criação
    do evento, portanto execuções concorrentes do beat não duplicam entrega.
    """
    now = iso_now()
    tenants = router.control.fetch_all("SELECT id FROM platform_tenants WHERE status='active' ORDER BY id")
    queued = 0; errors: list[dict[str, str]] = []
    for item in tenants:
        tenant_id = str(item["id"])
        try:
            store = router.tenant_store(tenant_id)
            rows = store.fetch_all(
                "SELECT id,channel FROM notifications WHERE tenant_id=? AND state='scheduled' AND scheduled_at IS NOT NULL AND scheduled_at<=? ORDER BY scheduled_at LIMIT 500",
                (tenant_id, now),
            )
            for row in rows:
                correlation_id = uuid7()
                with store.transaction() as conn:
                    current = conn.execute("SELECT state FROM notifications WHERE tenant_id=? AND id=?", (tenant_id, row["id"])).fetchone()
                    if not current or current["state"] != "scheduled":
                        continue
                    conn.execute("UPDATE notifications SET state='queued' WHERE tenant_id=? AND id=?", (tenant_id, row["id"]))
                    conn.execute(
                        "INSERT INTO notification_events(id,tenant_id,notification_id,event_type,state,details_json,occurred_at) VALUES(?,?,?,?,?,?,?)",
                        (uuid7(), tenant_id, row["id"], "schedule_due", "queued", "{}", now),
                    )
                    add_outbox(
                        conn, tenant_id=tenant_id, event_type="NotificationRequested", aggregate_type="notification",
                        aggregate_id=row["id"], payload={"notification_id": row["id"], "channel": row["channel"]},
                        correlation_id=correlation_id,
                    )
                    queued += 1
        except Exception as exc:
            errors.append({"tenant_id": tenant_id, "error": f"{type(exc).__name__}: {str(exc)[:300]}"})
    return {"status": "queued" if not errors else "partial", "tenants": len(tenants), "notifications": queued, "errors": errors}



def mark_overdue_workflow_tasks(*, router: DataRouter) -> dict[str, Any]:
    """Marca uma única vez tarefas humanas vencidas e publica evento de SLA.

    O estado da tarefa permanece ``open``: atraso não equivale a decisão humana.
    Automações podem reagir a ``WorkflowTaskSlaBreached`` para escalar, notificar
    ou abrir uma solicitação de acompanhamento.
    """
    now = iso_now()
    tenants = router.control.fetch_all("SELECT id FROM platform_tenants WHERE status='active' ORDER BY id")
    breached = 0; errors: list[dict[str, str]] = []
    for item in tenants:
        tenant_id = str(item["id"])
        try:
            store = router.tenant_store(tenant_id)
            rows = store.fetch_all(
                "SELECT id,workflow_instance_id,step_key,due_at FROM workflow_tasks WHERE tenant_id=? AND state='open' AND due_at IS NOT NULL AND due_at<=? AND sla_breached_at IS NULL ORDER BY due_at LIMIT 500",
                (tenant_id, now),
            )
            for row in rows:
                correlation_id = uuid7()
                with store.transaction() as conn:
                    current = conn.execute("SELECT state,sla_breached_at,escalation_count FROM workflow_tasks WHERE tenant_id=? AND id=?", (tenant_id, row["id"])).fetchone()
                    if not current or current["state"] != "open" or current["sla_breached_at"]:
                        continue
                    escalation_count = int(current["escalation_count"] or 0) + 1
                    conn.execute("UPDATE workflow_tasks SET sla_breached_at=?,escalation_count=?,version=version+1 WHERE tenant_id=? AND id=?", (now, escalation_count, tenant_id, row["id"]))
                    conn.execute(
                        "INSERT INTO workflow_events(id,tenant_id,workflow_instance_id,event_type,from_state,to_state,from_step_key,to_step_key,payload_json,occurred_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                        (uuid7(), tenant_id, row["workflow_instance_id"], "sla_breached", "active", "active", row["step_key"], row["step_key"], json.dumps({"task_id": row["id"], "due_at": row["due_at"], "escalation_count": escalation_count}, ensure_ascii=False, sort_keys=True), now),
                    )
                    add_outbox(
                        conn, tenant_id=tenant_id, event_type="WorkflowTaskSlaBreached", aggregate_type="workflow_instance",
                        aggregate_id=row["workflow_instance_id"], payload={"task_id": row["id"], "step_key": row["step_key"], "due_at": row["due_at"], "escalation_count": escalation_count}, correlation_id=correlation_id,
                    )
                    breached += 1
        except Exception as exc:
            errors.append({"tenant_id": tenant_id, "error": f"{type(exc).__name__}: {str(exc)[:300]}"})
    return {"status": "processed" if not errors else "partial", "tenants": len(tenants), "breached": breached, "errors": errors}

def schedule_ibpt_for_active_tenants(*, router: DataRouter) -> dict[str, Any]:
    """Agenda IBPT apenas para tenants com perfil publicado ``remote_sync``.

    O Beat permanece registrado continuamente. A decisão de executar é interna e
    por tenant, portanto ativar/publicar um perfil não exige reiniciar workers.
    O scheduler grava somente outbox; download e retry continuam no consumer.
    """
    tenants = router.control.fetch_all("SELECT id FROM platform_tenants WHERE status='active' ORDER BY id")
    runs = 0
    eligible = 0
    skipped = 0
    errors: list[dict[str, str]] = []
    today = date.today()
    for item in tenants:
        tenant_id = str(item["id"])
        try:
            store = router.tenant_store(tenant_id)
            profile = resolve_ibpt_profile(store, tenant_id, today)
            if not profile or profile["mode"] != "remote_sync" or not profile["sync_enabled"]:
                skipped += 1
                continue
            eligible += 1
            created = queue_ibpt_sync(store, tenant_id=tenant_id, ufs=list(UFS), actor_id=None, correlation_id=None)
            runs += len(created)
        except Exception as exc:
            errors.append({"tenant_id": tenant_id, "error": f"{type(exc).__name__}: {str(exc)[:300]}"})
    return {
        "status": "queued" if not errors else "partial",
        "tenants": len(tenants), "eligible_tenants": eligible, "skipped_tenants": skipped,
        "runs": runs, "errors": errors,
    }


if Celery is not None:
    celery_app = Celery("pige360")
    rabbit_password = _secret("RABBITMQ_PASSWORD", "RABBITMQ_PASSWORD_FILE")
    redis_password = _secret("REDIS_PASSWORD", "REDIS_PASSWORD_FILE")
    rabbit_url = _authenticated_url(
        os.getenv("RABBITMQ_URL", "amqp://pige360@127.0.0.1:5672/pige360"),
        rabbit_password,
        username="pige360",
    )
    redis_url = _authenticated_url(os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0"), redis_password)
    celery_app.conf.update(
        broker_url=rabbit_url,
        result_backend=redis_url,
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        task_acks_late=True,
        worker_prefetch_multiplier=1,
        task_reject_on_worker_lost=True,
        task_default_retry_delay=5,
        task_routes={"pige360.publish_outbox": {"queue": "default"}, "pige360.schedule_ibpt_sync": {"queue": "fiscal"}, "pige360.queue_due_notifications": {"queue": "notifications"}, "pige360.mark_overdue_workflow_tasks": {"queue": "default"}},
        beat_schedule={
            "publish-transactional-outbox": {
                "task": "pige360.publish_outbox",
                "schedule": float(os.getenv("OUTBOX_PUBLISH_INTERVAL_SECONDS", "2")),
            },
            "queue-due-notifications": {
                "task": "pige360.queue_due_notifications",
                "schedule": float(os.getenv("NOTIFICATION_SCHEDULER_INTERVAL_SECONDS", "60")),
            },
            "workflow-sla-watch": {
                "task": "pige360.mark_overdue_workflow_tasks",
                "schedule": float(os.getenv("WORKFLOW_SLA_INTERVAL_SECONDS", "60")),
            }
        },
    )
    celery_app.conf.beat_schedule["daily-ibpt-sync"] = {
        "task": "pige360.schedule_ibpt_sync",
        "schedule": float(os.getenv("IBPT_SYNC_INTERVAL_SECONDS", "86400")),
    }

    @celery_app.task(
        bind=True,
        autoretry_for=(TimeoutError, ConnectionError, OSError),
        retry_backoff=True,
        retry_jitter=True,
        max_retries=7,
        name="pige360.process_event",
    )
    def process_event(self: Any, envelope: dict[str, Any]) -> dict[str, Any]:
        secret = _secret("WORKER_CONTEXT_SIGNING_KEY", "WORKER_CONTEXT_SIGNING_KEY_FILE")
        try:
            return handle_event(envelope, router=get_data_router(), signing_secret=secret)
        except FiscalRetryScheduled as exc:
            # O countdown e o limite vêm da política fiscal versionada selecionada pelo tenant.
            # ``max_retries`` é número de novas tentativas, enquanto max_attempts inclui a original.
            raise self.retry(
                exc=exc,
                countdown=exc.delay_seconds,
                max_retries=max(0, exc.max_attempts - 1),
            )

    @celery_app.task(name="pige360.schedule_ibpt_sync")
    def schedule_ibpt_sync() -> dict[str, Any]:
        return schedule_ibpt_for_active_tenants(router=get_data_router())

    @celery_app.task(name="pige360.queue_due_notifications")
    def schedule_notifications() -> dict[str, Any]:
        return queue_due_notifications(router=get_data_router())

    @celery_app.task(name="pige360.mark_overdue_workflow_tasks")
    def schedule_workflow_sla() -> dict[str, Any]:
        return mark_overdue_workflow_tasks(router=get_data_router())

    @celery_app.task(
        bind=True,
        autoretry_for=(TimeoutError, ConnectionError, OSError),
        retry_backoff=True,
        retry_jitter=True,
        max_retries=7,
        name="pige360.publish_outbox",
    )
    def publish_outbox(self: Any) -> dict[str, Any]:
        secret = _secret("WORKER_CONTEXT_SIGNING_KEY", "WORKER_CONTEXT_SIGNING_KEY_FILE")
        if len(secret) < 32:
            raise RuntimeError("WORKER_CONTEXT_SIGNING_KEY ausente ou fraca")

        def send(envelope: dict[str, Any], queue: str) -> Any:
            return celery_app.send_task("pige360.process_event", args=[envelope], queue=queue)

        return publish_all_pending(router=get_data_router(), signing_secret=secret, send_task=send)
else:
    celery_app = None
