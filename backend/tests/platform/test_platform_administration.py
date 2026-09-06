from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from app.shared.security.auth import AuthService

from conftest import ALPHA_HOST, PASSWORD, PLATFORM_HOST


def test_tenant_lifecycle_uses_reason_version_audit_and_outbox(local_env):
    tenant_id = local_env.alpha_tenant["id"]
    support = local_env.client.post(
        f"/api/v1/platform/tenants/{tenant_id}/support-sessions",
        headers=local_env.platform_headers(),
        json={"reason": "Atendimento aberto antes da suspensão controlada", "minutes": 30},
    )
    assert support.status_code == 201, support.text
    initial_version = int(
        local_env.client.app.state.data_router.control.scalar(
            "SELECT version AS n FROM platform_tenants WHERE id=?", (tenant_id,)
        )
    )
    suspended = local_env.client.post(
        f"/api/v1/platform/tenants/{tenant_id}/suspend",
        headers=local_env.platform_headers(),
        json={"expected_version": initial_version, "reason": "Inadimplência confirmada pelo financeiro"},
    )
    assert suspended.status_code == 200, suspended.text
    assert suspended.json()["status"] == "suspended"
    assert suspended.json()["version"] == initial_version + 1
    assert suspended.json()["support_sessions_revoked"] == 1

    active_support = local_env.client.get(
        "/api/v1/platform/support-sessions",
        headers=local_env.platform_headers(),
        params={"tenant_id": tenant_id, "active_only": True},
    )
    assert active_support.status_code == 200, active_support.text
    assert support.json()["id"] not in {item["id"] for item in active_support.json()["items"]}

    support_while_suspended = local_env.client.post(
        f"/api/v1/platform/tenants/{tenant_id}/support-sessions",
        headers=local_env.platform_headers(),
        json={"reason": "Atendimento não pode reabrir durante suspensão", "minutes": 30},
    )
    assert support_while_suspended.status_code == 409, support_while_suspended.text
    assert support_while_suspended.json()["code"] == "TENANT_SUPPORT_UNAVAILABLE"

    blocked = local_env.client.get(
        "/api/v1/tenant/context",
        headers={"host": ALPHA_HOST, "Authorization": f"Bearer {local_env.alpha_token}"},
    )
    assert blocked.status_code == 503, blocked.text

    stale = local_env.client.post(
        f"/api/v1/platform/tenants/{tenant_id}/reactivate",
        headers=local_env.platform_headers(),
        json={"expected_version": initial_version, "reason": "Tentativa com versão administrativa obsoleta"},
    )
    assert stale.status_code == 409, stale.text
    assert stale.json()["code"] == "TENANT_VERSION_CONFLICT"

    reactivated = local_env.client.post(
        f"/api/v1/platform/tenants/{tenant_id}/reactivate",
        headers=local_env.platform_headers(),
        json={"expected_version": initial_version + 1, "reason": "Regularização financeira validada pelo operador"},
    )
    assert reactivated.status_code == 200, reactivated.text
    assert reactivated.json()["status"] == "active"
    assert reactivated.json()["version"] == initial_version + 2

    control = local_env.client.app.state.data_router.control
    actions = {
        row["action"]
        for row in control.fetch_all(
            "SELECT action FROM audit_log WHERE tenant_id=? AND aggregate_type='tenant'",
            (tenant_id,),
        )
    }
    events = {
        row["event_type"]
        for row in control.fetch_all(
            "SELECT event_type FROM outbox_events WHERE tenant_id=? AND aggregate_type='tenant'",
            (tenant_id,),
        )
    }
    assert {"suspend", "reactivate"}.issubset(actions)
    assert {"TenantSuspended", "TenantReactivated"}.issubset(events)


def test_tenant_quotas_are_validated_versioned_and_preserve_legacy_keys(local_env):
    tenant_id = local_env.alpha_tenant["id"]
    control = local_env.client.app.state.data_router.control
    control.execute(
        "UPDATE platform_tenants SET quotas_json=? WHERE id=?",
        (json.dumps({"legacy_reporting_limit": 7}), tenant_id),
    )
    current = local_env.client.get(
        f"/api/v1/platform/tenants/{tenant_id}/quotas",
        headers=local_env.platform_headers(),
    )
    assert current.status_code == 200, current.text
    assert current.json()["configured"]["legacy_reporting_limit"] == 7
    assert current.json()["effective"]["max_users"] == 500
    assert current.json()["enforcement"]["max_students"]["status"] == "enforced"
    assert current.json()["enforcement"]["storage_bytes"] == {
        "status": "not_enforced",
        "scope": "configured_advisory_limit",
        "reason_code": "STORAGE_USAGE_LEDGER_UNAVAILABLE",
    }

    updated = local_env.client.put(
        f"/api/v1/platform/tenants/{tenant_id}/quotas",
        headers=local_env.platform_headers(),
        json={
            "expected_version": current.json()["version"],
            "reason": "Ampliação de capacidade aprovada no contrato",
            "quotas": {"max_users": 800, "max_concurrent_builds": 4},
        },
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["configured"]["legacy_reporting_limit"] == 7
    assert body["effective"]["max_users"] == 800
    assert body["version"] == current.json()["version"] + 1

    unknown = local_env.client.put(
        f"/api/v1/platform/tenants/{tenant_id}/quotas",
        headers=local_env.platform_headers(),
        json={
            "expected_version": body["version"],
            "reason": "Campo desconhecido não pode entrar no contrato",
            "quotas": {"root_shell": 1},
        },
    )
    assert unknown.status_code == 422, unknown.text


def test_user_and_custom_domain_writes_enforce_tenant_quotas(local_env):
    tenant_id = local_env.alpha_tenant["id"]
    current = local_env.client.get(
        f"/api/v1/platform/tenants/{tenant_id}/quotas",
        headers=local_env.platform_headers(),
    )
    assert current.status_code == 200, current.text
    updated = local_env.client.put(
        f"/api/v1/platform/tenants/{tenant_id}/quotas",
        headers=local_env.platform_headers(),
        json={
            "expected_version": current.json()["version"],
            "reason": "Aplicação de limites mínimos para validar enforcement",
            "quotas": {"max_users": 1, "max_custom_domains": 0},
        },
    )
    assert updated.status_code == 200, updated.text

    user = local_env.client.post(
        "/api/v1/auth/users",
        headers=local_env.alpha_headers(),
        json={
            "email": "blocked-by-quota@alpha.example.com",
            "password": PASSWORD,
            "roles": ["secretary"],
        },
    )
    assert user.status_code == 409, user.text
    assert user.json()["code"] == "TENANT_QUOTA_EXCEEDED"

    domain = local_env.client.post(
        f"/api/v1/platform/tenants/{tenant_id}/domains",
        headers=local_env.platform_headers(),
        json={"hostname": "quota-blocked.alpha-example.com", "surface": "admin"},
    )
    assert domain.status_code == 409, domain.text
    assert domain.json()["code"] == "TENANT_QUOTA_EXCEEDED"


def test_support_session_can_be_revoked_with_audit_and_outbox(local_env):
    tenant_id = local_env.alpha_tenant["id"]
    created = local_env.client.post(
        f"/api/v1/platform/tenants/{tenant_id}/support-sessions",
        headers=local_env.platform_headers(),
        json={"reason": "Diagnóstico autorizado pelo responsável", "minutes": 30},
    )
    assert created.status_code == 201, created.text
    session_id = created.json()["id"]
    revoked = local_env.client.post(
        f"/api/v1/platform/support-sessions/{session_id}/revoke",
        headers=local_env.platform_headers(),
        json={"reason": "Atendimento concluído e acesso não é mais necessário"},
    )
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["state"] == "revoked"

    active = local_env.client.get(
        "/api/v1/platform/support-sessions",
        headers=local_env.platform_headers(),
        params={"tenant_id": tenant_id, "active_only": True},
    )
    assert active.status_code == 200, active.text
    assert session_id not in {item["id"] for item in active.json()["items"]}
    control = local_env.client.app.state.data_router.control
    assert control.scalar(
        "SELECT COUNT(*) AS n FROM audit_log WHERE aggregate_id=? AND action='support_session_revoked'",
        (session_id,),
    ) == 1
    assert control.scalar(
        "SELECT COUNT(*) AS n FROM outbox_events WHERE aggregate_id=? AND event_type='SupportSessionRevoked'",
        (session_id,),
    ) == 1


def test_support_assumed_user_must_be_active_and_belong_to_target_tenant(local_env):
    alpha_user, _ = local_env.create_alpha_user(
        "support-target@alpha.example.com",
        ["secretary"],
    )
    beta_store = local_env.client.app.state.data_router.tenant_store(local_env.beta_tenant["id"])
    beta_owner = beta_store.fetch_one(
        "SELECT id FROM users WHERE tenant_id=? AND email=?",
        (local_env.beta_tenant["id"], "owner@beta.example.com"),
    )
    assert beta_owner

    valid = local_env.client.post(
        f"/api/v1/platform/tenants/{local_env.alpha_tenant['id']}/support-sessions",
        headers=local_env.platform_headers(),
        json={
            "reason": "Suporte autorizado para usuário ativo do tenant",
            "assumed_user_id": alpha_user["id"],
        },
    )
    assert valid.status_code == 201, valid.text

    cross_tenant = local_env.client.post(
        f"/api/v1/platform/tenants/{local_env.alpha_tenant['id']}/support-sessions",
        headers=local_env.platform_headers(),
        json={
            "reason": "Tentativa controlada com usuário de outro tenant",
            "assumed_user_id": beta_owner["id"],
        },
    )
    assert cross_tenant.status_code == 409, cross_tenant.text
    assert cross_tenant.json()["code"] == "SUPPORT_ASSUMED_USER_INVALID"

    alpha_store = local_env.client.app.state.data_router.tenant_store(local_env.alpha_tenant["id"])
    alpha_store.execute("UPDATE users SET active=0 WHERE id=?", (alpha_user["id"],))
    inactive = local_env.client.post(
        f"/api/v1/platform/tenants/{local_env.alpha_tenant['id']}/support-sessions",
        headers=local_env.platform_headers(),
        json={
            "reason": "Tentativa controlada com usuário desativado no tenant",
            "assumed_user_id": alpha_user["id"],
        },
    )
    assert inactive.status_code == 409, inactive.text
    assert inactive.json()["code"] == "SUPPORT_ASSUMED_USER_INVALID"


def test_platform_status_is_degraded_and_sanitized_when_one_tenant_store_is_unavailable(local_env, monkeypatch):
    data_router = local_env.client.app.state.data_router
    original = data_router.tenant_store

    def tenant_store(tenant_id: str):
        if tenant_id == local_env.beta_tenant["id"]:
            raise RuntimeError("postgresql://operator:raw-secret@internal.example/tenant")
        return original(tenant_id)

    monkeypatch.setattr(data_router, "tenant_store", tenant_store)
    response = local_env.client.get(
        "/api/v1/platform/status",
        headers=local_env.platform_headers(),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "degraded"
    assert body["tenant_datastores"]["checked"] == 2
    assert body["tenant_datastores"]["available"] == 1
    assert body["tenant_datastores"]["unavailable"] == 1
    assert body["tenant_datastores"]["items"] == [{
        "tenant_id": local_env.beta_tenant["id"],
        "tenant_status": "active",
        "code": "TENANT_DATABASE_UNAVAILABLE",
    }]
    assert "raw-secret" not in response.text


def test_tenant_http_rate_quota_is_transactional_and_isolated(local_env):
    control = local_env.client.app.state.data_router.control
    tenant_id = local_env.alpha_tenant["id"]
    control.execute(
        "UPDATE platform_tenants SET quotas_json=? WHERE id=?",
        (json.dumps({"api_requests_per_minute": 1}), tenant_id),
    )
    control.execute("DELETE FROM tenant_api_rate_buckets WHERE tenant_id=?", (tenant_id,))

    allowed = local_env.client.get("/api/v1/auth/me", headers=local_env.alpha_headers())
    assert allowed.status_code == 200, allowed.text
    assert allowed.headers["x-ratelimit-limit"] == "1"
    assert allowed.headers["x-ratelimit-remaining"] == "0"

    blocked = local_env.client.get("/api/v1/auth/me", headers=local_env.alpha_headers())
    assert blocked.status_code == 429, blocked.text
    assert blocked.json()["code"] == "TENANT_API_RATE_LIMIT_EXCEEDED"
    assert int(blocked.headers["retry-after"]) >= 1

    beta = local_env.client.get("/api/v1/auth/me", headers=local_env.beta_headers())
    assert beta.status_code == 200, beta.text


def test_platform_inventory_is_sanitized_and_does_not_probe_external_providers(local_env):
    response = local_env.client.get(
        "/api/v1/platform/operations/inventory",
        headers=local_env.platform_headers(),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["external_provider_probes_performed"] is False
    assert body["control_database"]["state"] == "reachable"
    assert body["tenant_resources"]["total"] == 2
    assert body["tenant_resources"]["database_reachable"] == 2
    assert set(body["workloads"]["builds"]) == {"queued", "building", "failed", "completed"}
    serialized = response.text.lower()
    for forbidden in ("password", "secret", "ciphertext", "database_path", "storage_path", "access_key"):
        assert forbidden not in serialized


def test_platform_users_are_sanitized_and_deactivation_revokes_sessions(local_env):
    app = local_env.client.app
    service = AuthService(
        app.state.data_router.control,
        app.state.settings,
        tenant_id=None,
        plane="platform",
    )
    added = service.create_user(
        "operator@platform.example.com",
        PASSWORD,
        ["platform_admin"],
    )
    login = local_env.client.post(
        "/api/v1/auth/login",
        headers={"host": PLATFORM_HOST},
        json={"email": added["email"], "password": PASSWORD},
    )
    assert login.status_code == 200, login.text
    operator_token = login.json()["access_token"]

    listed = local_env.client.get("/api/v1/platform/users", headers=local_env.platform_headers())
    assert listed.status_code == 200, listed.text
    operator = next(item for item in listed.json()["items"] if item["id"] == added["id"])
    assert set(operator) == {"id", "email", "roles", "active", "created_at", "updated_at", "is_current_user"}

    current = next(item for item in listed.json()["items"] if item["is_current_user"])
    self_disable = local_env.client.patch(
        f"/api/v1/platform/users/{current['id']}/active",
        headers=local_env.platform_headers(),
        json={"active": False, "reason": "Tentativa de auto bloqueio deve ser recusada"},
    )
    assert self_disable.status_code == 409, self_disable.text
    assert self_disable.json()["code"] == "PLATFORM_ADMIN_SELF_DISABLE_FORBIDDEN"

    disabled = local_env.client.patch(
        f"/api/v1/platform/users/{added['id']}/active",
        headers=local_env.platform_headers(),
        json={"active": False, "reason": "Acesso administrativo encerrado por desligamento"},
    )
    assert disabled.status_code == 200, disabled.text
    assert disabled.json()["active"] is False
    denied = local_env.client.get(
        "/api/v1/platform/status",
        headers={"host": PLATFORM_HOST, "Authorization": f"Bearer {operator_token}"},
    )
    assert denied.status_code == 401, denied.text

    enabled = local_env.client.patch(
        f"/api/v1/platform/users/{added['id']}/active",
        headers=local_env.platform_headers(),
        json={"active": True, "reason": "Retorno do operador formalmente autorizado"},
    )
    assert enabled.status_code == 200, enabled.text
    assert enabled.json()["active"] is True


def test_cross_deactivation_cannot_remove_every_platform_super_admin(local_env):
    app = local_env.client.app
    service = AuthService(
        app.state.data_router.control,
        app.state.settings,
        tenant_id=None,
        plane="platform",
    )
    second = service.create_user(
        "second-root@platform.example.com",
        PASSWORD,
        ["platform_super_admin", "platform_admin"],
    )
    login = local_env.client.post(
        "/api/v1/auth/login",
        headers={"host": PLATFORM_HOST},
        json={"email": second["email"], "password": PASSWORD},
    )
    assert login.status_code == 200, login.text
    second_token = login.json()["access_token"]
    root_id = app.state.data_router.control.fetch_one(
        "SELECT id FROM users WHERE tenant_id IS NULL AND email=?",
        ("root@platform.example.com",),
    )["id"]
    barrier = Barrier(2)

    def deactivate(target_id: str, token: str, reason: str):
        barrier.wait(timeout=5)
        return local_env.client.patch(
            f"/api/v1/platform/users/{target_id}/active",
            headers={"host": PLATFORM_HOST, "Authorization": f"Bearer {token}"},
            json={"active": False, "reason": reason},
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        root_request = executor.submit(
            deactivate,
            second["id"],
            local_env.platform_token,
            "Desativação concorrente iniciada pela conta raiz",
        )
        second_request = executor.submit(
            deactivate,
            root_id,
            second_token,
            "Desativação concorrente iniciada pela segunda raiz",
        )
        responses = [root_request.result(), second_request.result()]

    assert sum(response.status_code == 200 for response in responses) == 1
    assert all(response.status_code in {200, 401, 409} for response in responses)
    active = app.state.data_router.control.fetch_all(
        "SELECT roles_json FROM users WHERE tenant_id IS NULL AND active=1"
    )
    active_super_admins = sum(
        1 for row in active if "platform_super_admin" in json.loads(row["roles_json"])
    )
    assert active_super_admins == 1
