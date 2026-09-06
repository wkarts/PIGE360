from __future__ import annotations

import json
import secrets
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Query, Request, Response

from app.modules.operational_control.presentation.schemas import (
    AgentHeartbeatInput,
    AgentJobStateInput,
    AgentRegistrationInput,
    AgentRevokeInput,
    OperationalJobCancelInput,
    OperationalJobCreate,
)
from app.modules.operational_control.providers import sanitized_provider_catalog
from app.modules.operational_control.service import (
    CAPABILITY_BY_OPERATION,
    JOB_LEASE_SECONDS,
    agent_token_hash,
    agent_view,
    audit_agent_snapshot,
    canonical_job_hash,
    capabilities_from_row,
    future_timestamp,
    generate_agent_token,
    job_view,
    now_iso,
)
from app.shared.domain.ids import uuid7
from app.shared.events.records import add_audit, add_outbox
from app.shared.presentation.errors import DomainError
from app.shared.security.auth import CurrentUser, require_roles


router = APIRouter(tags=["platform-operational-control"])


def _require_platform(user: CurrentUser) -> None:
    if user.plane != "platform":
        raise DomainError("PLATFORM_ROUTE_REQUIRED", "Rota global indisponível neste domínio.", 404)


def _agent_auth(
    request: Request,
    agent_token: Annotated[str | None, Header(alias="X-PIGE360-Agent-Token")] = None,
) -> dict:
    if request.state.host_resolution.plane != "platform":
        raise DomainError("PLATFORM_ROUTE_REQUIRED", "Rota global indisponível neste domínio.", 404)
    if not agent_token or len(agent_token) < 48 or len(agent_token) > 256:
        raise DomainError("OPERATIONAL_AGENT_AUTH_INVALID", "Credencial de agente inválida.", 401, "Não autenticado")
    digest = agent_token_hash(agent_token)
    row = request.state.store.fetch_one("SELECT * FROM operational_agents WHERE token_hash=?", (digest,))
    if (
        not row
        or row.get("state") != "active"
        or not secrets.compare_digest(str(row.get("token_hash") or ""), digest)
    ):
        raise DomainError("OPERATIONAL_AGENT_AUTH_INVALID", "Credencial de agente inválida.", 401, "Não autenticado")
    return row


def _job_or_404(request: Request, job_id: str) -> dict:
    row = request.state.store.fetch_one("SELECT * FROM operational_jobs WHERE id=?", (job_id,))
    if not row:
        raise DomainError("OPERATIONAL_JOB_NOT_FOUND", "Job operacional não localizado.", 404)
    return row


@router.post("/platform/operations/agents", operation_id="register_operational_agent", status_code=201)
def register_agent(
    data: AgentRegistrationInput,
    request: Request,
    response: Response,
    user: CurrentUser = Depends(require_roles("platform_super_admin")),
):
    _require_platform(user)
    token = generate_agent_token()
    token_hash = agent_token_hash(token)
    agent_id = uuid7()
    now = now_iso()
    record = {
        "id": agent_id,
        "name": data.name,
        "agent_type": data.agent_type,
        "capabilities_json": json.dumps(data.capabilities, separators=(",", ":")),
        "token_hash": token_hash,
        "software_version": data.software_version,
        "state": "active",
        "registered_by": user.id,
        "last_seen_at": None,
        "revoked_at": None,
        "created_at": now,
        "updated_at": now,
        "version": 1,
    }
    with request.state.store.transaction() as conn:
        request.state.store.transaction_lock(conn, f"operational-agent-name:{data.name}")
        existing = conn.execute("SELECT id FROM operational_agents WHERE name=?", (data.name,)).fetchone()
        if existing:
            raise DomainError("OPERATIONAL_AGENT_NAME_EXISTS", "Já existe um agente com este nome.", 409)
        conn.execute(
            """INSERT INTO operational_agents(
                   id,name,agent_type,capabilities_json,token_hash,software_version,state,registered_by,
                   last_seen_at,revoked_at,created_at,updated_at,version
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                record["id"], record["name"], record["agent_type"], record["capabilities_json"],
                record["token_hash"], record["software_version"], record["state"], record["registered_by"],
                None, None, now, now, 1,
            ),
        )
        safe = audit_agent_snapshot(record)
        add_audit(
            conn,
            tenant_id=None,
            actor_id=user.id,
            action="operational_agent_registered",
            aggregate_type="operational_agent",
            aggregate_id=agent_id,
            correlation_id=request.state.correlation_id,
            after=safe,
            reason=data.reason,
        )
        add_outbox(
            conn,
            tenant_id=None,
            event_type="OperationalAgentRegistered",
            aggregate_type="operational_agent",
            aggregate_id=agent_id,
            payload=safe,
            correlation_id=request.state.correlation_id,
        )
    response.headers["Cache-Control"] = "no-store"
    return {
        "agent": agent_view(record),
        "credential": {
            "token": token,
            "header": "X-PIGE360-Agent-Token",
            "shown_once": True,
        },
    }


@router.get("/platform/operations/agents", operation_id="list_operational_agents")
def list_agents(
    request: Request,
    include_revoked: bool = False,
    user: CurrentUser = Depends(require_roles("platform_super_admin", "platform_admin")),
):
    _require_platform(user)
    sql = "SELECT * FROM operational_agents"
    if not include_revoked:
        sql += " WHERE state='active'"
    sql += " ORDER BY name"
    return {"items": [agent_view(row) for row in request.state.store.fetch_all(sql)]}


@router.post(
    "/platform/operations/agents/{agent_id}/revoke",
    operation_id="revoke_operational_agent",
)
def revoke_agent(
    agent_id: str,
    data: AgentRevokeInput,
    request: Request,
    user: CurrentUser = Depends(require_roles("platform_super_admin")),
):
    _require_platform(user)
    now = now_iso()
    with request.state.store.transaction() as conn:
        request.state.store.transaction_lock(conn, f"operational-agent:{agent_id}")
        current_raw = conn.execute("SELECT * FROM operational_agents WHERE id=?", (agent_id,)).fetchone()
        if not current_raw:
            raise DomainError("OPERATIONAL_AGENT_NOT_FOUND", "Agente operacional não localizado.", 404)
        current = dict(current_raw)
        if int(current["version"]) != data.expected_version:
            raise DomainError("OPERATIONAL_AGENT_VERSION_CONFLICT", "O agente foi alterado por outro operador.", 409)
        if current["state"] == "revoked":
            return {**agent_view(current), "changed": False, "jobs_reassigned": 0}
        changed = conn.execute(
            """UPDATE operational_agents
               SET state='revoked',revoked_at=?,updated_at=?,version=version+1
               WHERE id=? AND state='active' AND version=?""",
            (now, now, agent_id, data.expected_version),
        ).rowcount
        if changed != 1:
            raise DomainError("OPERATIONAL_AGENT_VERSION_CONFLICT", "O agente foi alterado por outro operador.", 409)
        active_jobs_row = conn.execute(
            """SELECT COUNT(*) AS n FROM operational_jobs
               WHERE assigned_agent_id=? AND state IN ('claimed','running')""",
            (agent_id,),
        ).fetchone()
        active_jobs = int(active_jobs_row["n"] if active_jobs_row else 0)
        after = {**current, "state": "revoked", "revoked_at": now, "updated_at": now, "version": data.expected_version + 1}
        safe_after = audit_agent_snapshot(after)
        add_audit(
            conn,
            tenant_id=None,
            actor_id=user.id,
            action="operational_agent_revoked",
            aggregate_type="operational_agent",
            aggregate_id=agent_id,
            correlation_id=request.state.correlation_id,
            before=audit_agent_snapshot(current),
            after={**safe_after, "active_jobs_require_attention": active_jobs},
            reason=data.reason,
        )
        add_outbox(
            conn,
            tenant_id=None,
            event_type="OperationalAgentRevoked",
            aggregate_type="operational_agent",
            aggregate_id=agent_id,
            payload={**safe_after, "active_jobs_require_attention": active_jobs},
            correlation_id=request.state.correlation_id,
        )
    return {
        **agent_view(after),
        "changed": True,
        "jobs_reassigned": 0,
        "active_jobs_require_attention": active_jobs,
    }


@router.post("/platform/operations/agent/heartbeat", operation_id="heartbeat_operational_agent")
def heartbeat_agent(
    data: AgentHeartbeatInput,
    request: Request,
    agent: dict = Depends(_agent_auth),
):
    now = now_iso()
    software_version = data.software_version or agent.get("software_version")
    changed = request.state.store.execute(
        """UPDATE operational_agents SET last_seen_at=?,software_version=?,updated_at=?
           WHERE id=? AND state='active'""",
        (now, software_version, now, agent["id"]),
    )
    if changed != 1:
        raise DomainError("OPERATIONAL_AGENT_AUTH_INVALID", "Credencial de agente inválida.", 401, "Não autenticado")
    current = request.state.store.fetch_one("SELECT * FROM operational_agents WHERE id=?", (agent["id"],))
    return {"agent": agent_view(current or agent), "server_time": now}


@router.get("/platform/operations/providers", operation_id="list_operational_providers")
def list_providers(
    request: Request,
    user: CurrentUser = Depends(require_roles("platform_super_admin", "platform_admin")),
):
    _require_platform(user)
    return sanitized_provider_catalog(request.app.state.settings)


@router.post("/platform/operations/jobs", operation_id="queue_operational_job", status_code=202)
def queue_job(
    data: OperationalJobCreate,
    request: Request,
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            min_length=8,
            max_length=200,
            pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,199}$",
        ),
    ],
    user: CurrentUser = Depends(require_roles("platform_super_admin", "platform_admin")),
):
    _require_platform(user)
    if data.tenant_id and not request.state.store.fetch_one(
        "SELECT id FROM platform_tenants WHERE id=?", (data.tenant_id,)
    ):
        raise DomainError("TENANT_NOT_FOUND", "Tenant não localizado.", 404)

    payload = data.model_dump(mode="json")
    request_hash = canonical_job_hash(payload)
    capability = CAPABILITY_BY_OPERATION[data.operation_type]
    now = now_iso()
    job_id = uuid7()
    replayed = False
    with request.state.store.transaction() as conn:
        request.state.store.transaction_lock(
            conn, f"operational-job-idempotency:{data.operation_type}:{idempotency_key}"
        )
        existing_raw = conn.execute(
            "SELECT * FROM operational_jobs WHERE operation_type=? AND idempotency_key=?",
            (data.operation_type, idempotency_key),
        ).fetchone()
        if existing_raw:
            existing = dict(existing_raw)
            if not secrets.compare_digest(str(existing["request_hash"]), request_hash):
                raise DomainError(
                    "IDEMPOTENCY_KEY_REUSED",
                    "A chave de idempotência já foi usada com outro pedido.",
                    409,
                )
            job_id = existing["id"]
            replayed = True
        else:
            conn.execute(
                """INSERT INTO operational_jobs(
                       id,operation_type,resource_scope,tenant_id,required_capability,deployment_target,
                       image_mode,release_version,backup_reference,idempotency_key,request_hash,reason,
                       requested_by,correlation_id,created_at,updated_at
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    job_id, data.operation_type, data.resource_scope, data.tenant_id, capability,
                    data.deployment_target, data.image_mode, data.release_version, data.backup_reference,
                    idempotency_key, request_hash, data.reason, user.id, request.state.correlation_id, now, now,
                ),
            )
            event_payload = {
                "id": job_id,
                "operation_type": data.operation_type,
                "resource_scope": data.resource_scope,
                "tenant_id": data.tenant_id,
                "required_capability": capability,
                "state": "queued",
            }
            add_audit(
                conn,
                tenant_id=data.tenant_id,
                actor_id=user.id,
                action="operational_job_queued",
                aggregate_type="operational_job",
                aggregate_id=job_id,
                correlation_id=request.state.correlation_id,
                after=event_payload,
                reason=data.reason,
            )
            add_outbox(
                conn,
                tenant_id=data.tenant_id,
                event_type="OperationalJobQueued",
                aggregate_type="operational_job",
                aggregate_id=job_id,
                payload=event_payload,
                correlation_id=request.state.correlation_id,
            )
    result = _job_or_404(request, job_id)
    return {"job": job_view(result), "replayed": replayed, "execution_started": False}


@router.get("/platform/operations/jobs", operation_id="list_operational_jobs")
def list_jobs(
    request: Request,
    operation_type: Literal["backup", "restore", "deploy"] | None = None,
    job_state: Annotated[
        Literal["queued", "claimed", "running", "succeeded", "failed", "cancelled"] | None,
        Query(alias="state"),
    ] = None,
    tenant_id: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=100, ge=1, le=500),
    user: CurrentUser = Depends(require_roles("platform_super_admin", "platform_admin")),
):
    _require_platform(user)
    sql = "SELECT * FROM operational_jobs WHERE 1=1"
    params: list[object] = []
    if operation_type:
        sql += " AND operation_type=?"
        params.append(operation_type)
    if job_state:
        sql += " AND state=?"
        params.append(job_state)
    if tenant_id:
        sql += " AND tenant_id=?"
        params.append(tenant_id)
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    return {"items": [job_view(row) for row in request.state.store.fetch_all(sql, params)], "limit": limit}


@router.get("/platform/operations/jobs/{job_id}", operation_id="get_operational_job")
def get_job(
    job_id: str,
    request: Request,
    user: CurrentUser = Depends(require_roles("platform_super_admin", "platform_admin")),
):
    _require_platform(user)
    return job_view(_job_or_404(request, job_id))


@router.post("/platform/operations/jobs/{job_id}/cancel", operation_id="cancel_operational_job")
def cancel_job(
    job_id: str,
    data: OperationalJobCancelInput,
    request: Request,
    user: CurrentUser = Depends(require_roles("platform_super_admin", "platform_admin")),
):
    _require_platform(user)
    now = now_iso()
    with request.state.store.transaction() as conn:
        request.state.store.transaction_lock(conn, f"operational-job:{job_id}")
        current_raw = conn.execute("SELECT * FROM operational_jobs WHERE id=?", (job_id,)).fetchone()
        if not current_raw:
            raise DomainError("OPERATIONAL_JOB_NOT_FOUND", "Job operacional não localizado.", 404)
        current = dict(current_raw)
        if int(current["version"]) != data.expected_version:
            raise DomainError("OPERATIONAL_JOB_VERSION_CONFLICT", "O job foi alterado por outro participante.", 409)
        if current["state"] != "queued":
            raise DomainError(
                "OPERATIONAL_JOB_CANNOT_CANCEL",
                "Somente um job ainda não reivindicado pode ser cancelado com segurança.",
                409,
            )
        changed = conn.execute(
            """UPDATE operational_jobs
               SET state='cancelled',finished_at=?,updated_at=?,version=version+1
               WHERE id=? AND state='queued' AND version=?""",
            (now, now, job_id, data.expected_version),
        ).rowcount
        if changed != 1:
            raise DomainError("OPERATIONAL_JOB_VERSION_CONFLICT", "O job foi alterado por outro participante.", 409)
        event_payload = {"id": job_id, "state": "cancelled", "version": data.expected_version + 1}
        add_audit(
            conn,
            tenant_id=current.get("tenant_id"),
            actor_id=user.id,
            action="operational_job_cancelled",
            aggregate_type="operational_job",
            aggregate_id=job_id,
            correlation_id=request.state.correlation_id,
            before={"state": "queued", "version": data.expected_version},
            after=event_payload,
            reason=data.reason,
        )
        add_outbox(
            conn,
            tenant_id=current.get("tenant_id"),
            event_type="OperationalJobCancelled",
            aggregate_type="operational_job",
            aggregate_id=job_id,
            payload=event_payload,
            correlation_id=request.state.correlation_id,
        )
    return job_view(_job_or_404(request, job_id))


@router.post("/platform/operations/agent/jobs/claim", operation_id="claim_operational_job")
def claim_job(request: Request, agent: dict = Depends(_agent_auth)):
    capabilities = set(capabilities_from_row(agent))
    if not capabilities:
        raise DomainError("OPERATIONAL_AGENT_CAPABILITIES_INVALID", "O agente não possui capability válida.", 403)
    now = now_iso()
    lease_expires = future_timestamp(JOB_LEASE_SECONDS)
    claimed_id: str | None = None
    with request.state.store.transaction() as conn:
        request.state.store.transaction_lock(conn, "operational-job-claim")
        conn.execute(
            "UPDATE operational_agents SET last_seen_at=?,updated_at=? WHERE id=? AND state='active'",
            (now, now, agent["id"]),
        )
        candidates = conn.execute(
            "SELECT * FROM operational_jobs WHERE state='queued' ORDER BY created_at LIMIT 200"
        ).fetchall()
        for raw in candidates:
            candidate = dict(raw)
            if candidate["required_capability"] not in capabilities:
                continue
            changed = conn.execute(
                """UPDATE operational_jobs
                   SET state='claimed',assigned_agent_id=?,attempts=attempts+1,claimed_at=?,
                       lease_expires_at=?,updated_at=?,version=version+1
                   WHERE id=? AND state='queued' AND assigned_agent_id IS NULL""",
                (agent["id"], now, lease_expires, now, candidate["id"]),
            ).rowcount
            if changed != 1:
                continue
            claimed_id = candidate["id"]
            event_payload = {
                "id": claimed_id,
                "state": "claimed",
                "assigned_agent_id": agent["id"],
                "attempt": int(candidate["attempts"]) + 1,
            }
            add_audit(
                conn,
                tenant_id=candidate.get("tenant_id"),
                actor_id=None,
                action="operational_job_claimed",
                aggregate_type="operational_job",
                aggregate_id=claimed_id,
                correlation_id=request.state.correlation_id,
                before={"state": "queued"},
                after=event_payload,
            )
            add_outbox(
                conn,
                tenant_id=candidate.get("tenant_id"),
                event_type="OperationalJobClaimed",
                aggregate_type="operational_job",
                aggregate_id=claimed_id,
                payload=event_payload,
                correlation_id=request.state.correlation_id,
            )
            break
    if claimed_id is None:
        return {"job": None, "server_time": now, "lease_seconds": JOB_LEASE_SECONDS}
    return {
        "job": job_view(_job_or_404(request, claimed_id)),
        "server_time": now,
        "lease_seconds": JOB_LEASE_SECONDS,
    }


@router.post(
    "/platform/operations/agent/jobs/{job_id}/state",
    operation_id="report_operational_job_state",
)
def report_job_state(
    job_id: str,
    data: AgentJobStateInput,
    request: Request,
    agent: dict = Depends(_agent_auth),
):
    now = now_iso()
    capabilities = set(capabilities_from_row(agent))
    with request.state.store.transaction() as conn:
        request.state.store.transaction_lock(conn, f"operational-job:{job_id}")
        current_raw = conn.execute("SELECT * FROM operational_jobs WHERE id=?", (job_id,)).fetchone()
        if not current_raw:
            raise DomainError("OPERATIONAL_JOB_NOT_FOUND", "Job operacional não localizado.", 404)
        current = dict(current_raw)
        if current.get("assigned_agent_id") != agent["id"]:
            raise DomainError("OPERATIONAL_JOB_AGENT_MISMATCH", "O job pertence a outro agente.", 403)
        if current["required_capability"] not in capabilities:
            raise DomainError("OPERATIONAL_AGENT_CAPABILITY_REQUIRED", "Capability incompatível com o job.", 403)
        if int(current["version"]) != data.expected_version:
            raise DomainError("OPERATIONAL_JOB_VERSION_CONFLICT", "O job foi alterado por outro participante.", 409)
        allowed = {
            "claimed": {"running", "failed"},
            "running": {"running", "succeeded", "failed"},
        }
        if data.state not in allowed.get(current["state"], set()):
            raise DomainError(
                "OPERATIONAL_JOB_TRANSITION_INVALID",
                f"Transição de '{current['state']}' para '{data.state}' não permitida.",
                409,
            )
        if data.state == "succeeded" and current["operation_type"] == "backup" and not data.evidence_sha256:
            raise DomainError(
                "OPERATIONAL_JOB_EVIDENCE_REQUIRED",
                "Backup concluído exige o SHA-256 do artefato.",
                422,
            )

        started_at = current.get("started_at") or (now if data.state == "running" else None)
        terminal = data.state in {"succeeded", "failed"}
        finished_at = now if terminal else None
        lease_expires = None if terminal else future_timestamp(JOB_LEASE_SECONDS)
        changed = conn.execute(
            """UPDATE operational_jobs
               SET state=?,result_code=?,evidence_reference=?,evidence_sha256=?,failure_code=?,
                   started_at=?,finished_at=?,lease_expires_at=?,updated_at=?,version=version+1
               WHERE id=? AND state=? AND version=? AND assigned_agent_id=?""",
            (
                data.state, data.result_code, data.evidence_reference, data.evidence_sha256,
                data.failure_code, started_at, finished_at, lease_expires, now, job_id,
                current["state"], data.expected_version, agent["id"],
            ),
        ).rowcount
        if changed != 1:
            raise DomainError("OPERATIONAL_JOB_VERSION_CONFLICT", "O job foi alterado por outro participante.", 409)
        conn.execute(
            "UPDATE operational_agents SET last_seen_at=?,updated_at=? WHERE id=? AND state='active'",
            (now, now, agent["id"]),
        )
        event_payload = {
            "id": job_id,
            "state": data.state,
            "assigned_agent_id": agent["id"],
            "result_code": data.result_code,
            "evidence_reference": data.evidence_reference,
            "evidence_sha256": data.evidence_sha256,
            "failure_code": data.failure_code,
            "version": data.expected_version + 1,
        }
        add_audit(
            conn,
            tenant_id=current.get("tenant_id"),
            actor_id=None,
            action=f"operational_job_{data.state}",
            aggregate_type="operational_job",
            aggregate_id=job_id,
            correlation_id=request.state.correlation_id,
            before={"state": current["state"], "version": data.expected_version},
            after=event_payload,
        )
        add_outbox(
            conn,
            tenant_id=current.get("tenant_id"),
            event_type={
                "running": "OperationalJobStarted",
                "succeeded": "OperationalJobSucceeded",
                "failed": "OperationalJobFailed",
            }[data.state],
            aggregate_type="operational_job",
            aggregate_id=job_id,
            payload=event_payload,
            correlation_id=request.state.correlation_id,
        )
    return job_view(_job_or_404(request, job_id))
