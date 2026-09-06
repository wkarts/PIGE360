from __future__ import annotations

import hashlib
import json

from conftest import ALPHA_HOST


def _register(local_env, name: str, capabilities: list[str], agent_type: str = "multi") -> tuple[dict, str]:
    response = local_env.client.post(
        "/api/v1/platform/operations/agents",
        headers=local_env.platform_headers(),
        json={
            "name": name,
            "agent_type": agent_type,
            "capabilities": capabilities,
            "software_version": "1.1.0",
            "reason": "Registro controlado para execução operacional",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return body["agent"], body["credential"]["token"]


def _queue(local_env, operation: dict, key: str) -> dict:
    response = local_env.client.post(
        "/api/v1/platform/operations/jobs",
        headers=local_env.platform_headers(**{"Idempotency-Key": key}),
        json=operation,
    )
    assert response.status_code == 202, response.text
    return response.json()


def _agent_headers(local_env, token: str) -> dict[str, str]:
    return local_env.headers("api.platform.local", **{"X-PIGE360-Agent-Token": token})


def test_agent_lifecycle_uses_one_time_hash_heartbeat_stale_and_revoke(local_env):
    agent, token = _register(local_env, "backup-host-01", ["backup.execute"], "backup")
    assert agent["connectivity"] == "registered"
    assert agent["version"] == 1
    assert token.startswith("pige360_agent_")

    control = local_env.client.app.state.data_router.control
    stored = control.fetch_one("SELECT * FROM operational_agents WHERE id=?", (agent["id"],))
    assert stored is not None
    assert stored["token_hash"] == hashlib.sha256(token.encode()).hexdigest()
    assert token not in json.dumps(stored)
    audit_payload = control.fetch_one(
        "SELECT after_json FROM audit_log WHERE aggregate_id=? AND action='operational_agent_registered'",
        (agent["id"],),
    )
    outbox_payload = control.fetch_one(
        "SELECT payload_json FROM outbox_events WHERE aggregate_id=? AND event_type='OperationalAgentRegistered'",
        (agent["id"],),
    )
    assert audit_payload and outbox_payload
    assert token not in audit_payload["after_json"]
    assert token not in outbox_payload["payload_json"]
    assert "token_hash" not in audit_payload["after_json"]
    assert "token_hash" not in outbox_payload["payload_json"]

    listed = local_env.client.get(
        "/api/v1/platform/operations/agents", headers=local_env.platform_headers()
    )
    assert listed.status_code == 200, listed.text
    assert token not in listed.text
    assert "token_hash" not in listed.text

    heartbeat = local_env.client.post(
        "/api/v1/platform/operations/agent/heartbeat",
        headers=_agent_headers(local_env, token),
        json={"software_version": "1.1.1"},
    )
    assert heartbeat.status_code == 200, heartbeat.text
    assert heartbeat.json()["agent"]["connectivity"] == "online"
    assert heartbeat.json()["agent"]["version"] == 1

    control.execute(
        "UPDATE operational_agents SET last_seen_at=? WHERE id=?",
        ("2020-01-01T00:00:00Z", agent["id"]),
    )
    stale = local_env.client.get(
        "/api/v1/platform/operations/agents", headers=local_env.platform_headers()
    )
    stale_agent = next(item for item in stale.json()["items"] if item["id"] == agent["id"])
    assert stale_agent["connectivity"] == "stale"

    revoked = local_env.client.post(
        f"/api/v1/platform/operations/agents/{agent['id']}/revoke",
        headers=local_env.platform_headers(),
        json={"expected_version": 1, "reason": "Host retirado definitivamente da operação"},
    )
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["connectivity"] == "revoked"
    assert revoked.json()["jobs_reassigned"] == 0
    denied = local_env.client.post(
        "/api/v1/platform/operations/agent/heartbeat",
        headers=_agent_headers(local_env, token),
        json={},
    )
    assert denied.status_code == 401, denied.text
    assert control.scalar(
        "SELECT COUNT(*) AS n FROM audit_log WHERE aggregate_id=? AND action='operational_agent_revoked'",
        (agent["id"],),
    ) == 1
    assert control.scalar(
        "SELECT COUNT(*) AS n FROM outbox_events WHERE aggregate_id=? AND event_type='OperationalAgentRevoked'",
        (agent["id"],),
    ) == 1


def test_provider_catalog_is_configuration_only_and_sanitized(local_env, monkeypatch, tmp_path):
    secret_file = tmp_path / "cloudflare-token"
    secret_file.write_text("never-return-this-value", encoding="utf-8")
    monkeypatch.setenv("CLOUDFLARE_ENABLED", "true")
    monkeypatch.setenv("CLOUDFLARE_TENANT_ZONE_ID", "zone-secret-value")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN_FILE", str(secret_file))
    monkeypatch.setenv("LOKI_ENABLED", "true")
    monkeypatch.setenv("LOKI_INTERNAL_URL", "http://private-loki:3100")

    response = local_env.client.get(
        "/api/v1/platform/operations/providers", headers=local_env.platform_headers()
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["external_probe_performed"] is False
    assert body["status_scope"] == "configuration_only"
    items = {item["code"]: item for item in body["items"]}
    assert {
        "control_database",
        "tenant_database",
        "object_storage",
        "redis",
        "rabbitmq",
        "cloudflare",
        "loki",
        "connect_api",
        "mail",
    } == set(items)
    assert items["cloudflare"]["state"] == "configured_not_probed"
    assert items["loki"]["state"] == "configured_not_probed"
    assert items["control_database"]["state"] == "local_fallback"
    serialized = response.text.lower()
    for forbidden in (
        "never-return-this-value",
        "zone-secret-value",
        "private-loki",
        "cloudflare-token",
        "password",
        "access_key",
        "token_file",
    ):
        assert forbidden not in serialized

    tenant_denied = local_env.client.get(
        "/api/v1/platform/operations/providers",
        headers={"host": ALPHA_HOST, "Authorization": f"Bearer {local_env.alpha_token}"},
    )
    assert tenant_denied.status_code in {403, 404}


def test_jobs_are_typed_idempotent_queued_and_never_claim_execution_without_agent(local_env):
    operation = {
        "operation_type": "backup",
        "resource_scope": "platform",
        "reason": "Backup integral anterior à atualização programada",
    }
    created = _queue(local_env, operation, "backup-release-001")
    job = created["job"]
    assert job["state"] == "queued"
    assert job["assigned_agent_id"] is None
    assert created["execution_started"] is False

    replay = _queue(local_env, operation, "backup-release-001")
    assert replay["replayed"] is True
    assert replay["job"]["id"] == job["id"]

    changed = local_env.client.post(
        "/api/v1/platform/operations/jobs",
        headers=local_env.platform_headers(**{"Idempotency-Key": "backup-release-001"}),
        json={**operation, "reason": "Outro pedido não pode reutilizar a mesma chave"},
    )
    assert changed.status_code == 409, changed.text
    assert changed.json()["code"] == "IDEMPOTENCY_KEY_REUSED"

    command_injection = local_env.client.post(
        "/api/v1/platform/operations/jobs",
        headers=local_env.platform_headers(**{"Idempotency-Key": "backup-release-002"}),
        json={**operation, "command": "sh -c dangerous"},
    )
    assert command_injection.status_code == 422, command_injection.text

    unsafe_reference = local_env.client.post(
        "/api/v1/platform/operations/jobs",
        headers=local_env.platform_headers(**{"Idempotency-Key": "restore-release-001"}),
        json={
            "operation_type": "restore",
            "resource_scope": "platform",
            "backup_reference": "../../runtime-secrets/key",
            "reason": "Referência livre de caminho deve ser bloqueada",
        },
    )
    assert unsafe_reference.status_code == 422, unsafe_reference.text

    control = local_env.client.app.state.data_router.control
    stored = control.fetch_one("SELECT state,assigned_agent_id,result_code FROM operational_jobs WHERE id=?", (job["id"],))
    assert stored == {"state": "queued", "assigned_agent_id": None, "result_code": None}
    assert control.scalar(
        "SELECT COUNT(*) AS n FROM audit_log WHERE aggregate_id=? AND action='operational_job_queued'",
        (job["id"],),
    ) == 1


def test_capability_claim_state_evidence_lease_and_safe_cancellation(local_env):
    deploy = _queue(
        local_env,
        {
            "operation_type": "deploy",
            "resource_scope": "platform",
            "release_version": "1.1.0",
            "deployment_target": "cloudpanel",
            "image_mode": "registry",
            "reason": "Implantação aprovada para a versão estável",
        },
        "deploy-1-1-0-prod",
    )["job"]
    backup = _queue(
        local_env,
        {
            "operation_type": "backup",
            "resource_scope": "tenant",
            "tenant_id": local_env.alpha_tenant["id"],
            "reason": "Cópia de segurança solicitada pela operação",
        },
        "backup-alpha-001",
    )["job"]
    backup_agent, backup_token = _register(
        local_env, "backup-agent-02", ["backup.execute"], "backup"
    )

    claimed = local_env.client.post(
        "/api/v1/platform/operations/agent/jobs/claim",
        headers=_agent_headers(local_env, backup_token),
    )
    assert claimed.status_code == 200, claimed.text
    claimed_job = claimed.json()["job"]
    assert claimed_job["id"] == backup["id"]
    assert claimed_job["state"] == "claimed"
    assert claimed_job["assigned_agent_id"] == backup_agent["id"]
    assert claimed_job["attempts"] == 1

    direct_success = local_env.client.post(
        f"/api/v1/platform/operations/agent/jobs/{backup['id']}/state",
        headers=_agent_headers(local_env, backup_token),
        json={
            "expected_version": claimed_job["version"],
            "state": "succeeded",
            "result_code": "BACKUP_COMPLETED",
            "evidence_reference": "backup:alpha:001",
            "evidence_sha256": "a" * 64,
        },
    )
    assert direct_success.status_code == 409, direct_success.text

    running = local_env.client.post(
        f"/api/v1/platform/operations/agent/jobs/{backup['id']}/state",
        headers=_agent_headers(local_env, backup_token),
        json={"expected_version": claimed_job["version"], "state": "running"},
    )
    assert running.status_code == 200, running.text
    running_job = running.json()
    assert running_job["state"] == "running"

    no_digest = local_env.client.post(
        f"/api/v1/platform/operations/agent/jobs/{backup['id']}/state",
        headers=_agent_headers(local_env, backup_token),
        json={
            "expected_version": running_job["version"],
            "state": "succeeded",
            "result_code": "BACKUP_COMPLETED",
            "evidence_reference": "backup:alpha:001",
        },
    )
    assert no_digest.status_code == 422, no_digest.text
    assert no_digest.json()["code"] == "OPERATIONAL_JOB_EVIDENCE_REQUIRED"

    succeeded = local_env.client.post(
        f"/api/v1/platform/operations/agent/jobs/{backup['id']}/state",
        headers=_agent_headers(local_env, backup_token),
        json={
            "expected_version": running_job["version"],
            "state": "succeeded",
            "result_code": "BACKUP_COMPLETED",
            "evidence_reference": "backup:alpha:001",
            "evidence_sha256": "a" * 64,
        },
    )
    assert succeeded.status_code == 200, succeeded.text
    assert succeeded.json()["state"] == "succeeded"
    assert succeeded.json()["finished_at"]

    incompatible = local_env.client.post(
        "/api/v1/platform/operations/agent/jobs/claim",
        headers=_agent_headers(local_env, backup_token),
    )
    assert incompatible.status_code == 200, incompatible.text
    assert incompatible.json()["job"] is None
    assert local_env.client.get(
        f"/api/v1/platform/operations/jobs/{deploy['id']}", headers=local_env.platform_headers()
    ).json()["state"] == "queued"

    cancelled = local_env.client.post(
        f"/api/v1/platform/operations/jobs/{deploy['id']}/cancel",
        headers=local_env.platform_headers(),
        json={"expected_version": deploy["version"], "reason": "Janela de implantação formalmente cancelada"},
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["state"] == "cancelled"

    control = local_env.client.app.state.data_router.control
    control.execute(
        "UPDATE operational_jobs SET lease_expires_at=? WHERE id=?",
        ("2020-01-01T00:00:00Z", backup["id"]),
    )
    # Jobs terminais não voltam para a fila nem são classificados como lease expirado.
    terminal = local_env.client.get(
        f"/api/v1/platform/operations/jobs/{backup['id']}", headers=local_env.platform_headers()
    ).json()
    assert terminal["state"] == "succeeded"
    assert terminal["lease_expired"] is False
    actions = {
        row["action"]
        for row in control.fetch_all(
            "SELECT action FROM audit_log WHERE aggregate_id=? ORDER BY created_at", (backup["id"],)
        )
    }
    assert {
        "operational_job_queued",
        "operational_job_claimed",
        "operational_job_running",
        "operational_job_succeeded",
    } <= actions


def test_claimed_job_with_expired_lease_requires_attention_and_is_not_requeued(local_env):
    job = _queue(
        local_env,
        {
            "operation_type": "restore",
            "resource_scope": "platform",
            "backup_reference": "backup:platform:20260904",
            "reason": "Restauração controlada solicitada em homologação",
        },
        "restore-platform-001",
    )["job"]
    agent, token = _register(local_env, "restore-agent-01", ["restore.execute"], "restore")
    claimed = local_env.client.post(
        "/api/v1/platform/operations/agent/jobs/claim", headers=_agent_headers(local_env, token)
    )
    assert claimed.status_code == 200, claimed.text
    assert claimed.json()["job"]["id"] == job["id"]

    control = local_env.client.app.state.data_router.control
    control.execute(
        "UPDATE operational_jobs SET lease_expires_at=? WHERE id=?",
        ("2020-01-01T00:00:00Z", job["id"]),
    )
    observed = local_env.client.get(
        f"/api/v1/platform/operations/jobs/{job['id']}", headers=local_env.platform_headers()
    )
    assert observed.status_code == 200, observed.text
    assert observed.json()["state"] == "claimed"
    assert observed.json()["lease_expired"] is True
    assert observed.json()["attention_required"] is True

    other, other_token = _register(local_env, "restore-agent-02", ["restore.execute"], "restore")
    assert other["id"] != agent["id"]
    not_requeued = local_env.client.post(
        "/api/v1/platform/operations/agent/jobs/claim",
        headers=_agent_headers(local_env, other_token),
    )
    assert not_requeued.status_code == 200, not_requeued.text
    assert not_requeued.json()["job"] is None

    revoked = local_env.client.post(
        f"/api/v1/platform/operations/agents/{agent['id']}/revoke",
        headers=local_env.platform_headers(),
        json={"expected_version": 1, "reason": "Agente sem heartbeat removido da operação"},
    )
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["active_jobs_require_attention"] == 1
    assert revoked.json()["jobs_reassigned"] == 0


def test_operational_schema_and_migration_chain_are_additive(local_env):
    control = local_env.client.app.state.data_router.control
    agent_columns = {
        row["name"]
        for row in control.fetch_all("PRAGMA table_info(operational_agents)")
    }
    job_columns = {
        row["name"]
        for row in control.fetch_all("PRAGMA table_info(operational_jobs)")
    }
    assert {"token_hash", "capabilities_json", "last_seen_at", "revoked_at", "version"} <= agent_columns
    assert {
        "operation_type",
        "required_capability",
        "state",
        "request_hash",
        "assigned_agent_id",
        "lease_expires_at",
        "evidence_sha256",
        "version",
    } <= job_columns

    from importlib import import_module

    migration = import_module("alembic_control.versions.0006_operational_control")
    assert migration.revision == "0006_operational_control"
    assert migration.down_revision == "0005_tenant_api_rate_quota"

    openapi = local_env.client.get(
        "/api/v1/openapi.json", headers={"host": "api.platform.local"}
    )
    assert openapi.status_code == 200, openapi.text
    assert {
        "/api/v1/platform/operations/agents",
        "/api/v1/platform/operations/agent/heartbeat",
        "/api/v1/platform/operations/providers",
        "/api/v1/platform/operations/jobs",
        "/api/v1/platform/operations/agent/jobs/claim",
        "/api/v1/platform/operations/agent/jobs/{job_id}/state",
    } <= set(openapi.json()["paths"])
