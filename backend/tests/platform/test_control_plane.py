from __future__ import annotations

from conftest import ALPHA_HOST, PLATFORM_HOST


def test_platform_status_audit_and_support_session_are_operational(local_env):
    status = local_env.client.get("/api/v1/platform/status", headers=local_env.platform_headers())
    assert status.status_code == 200, status.text
    body = status.json()
    assert body["status"] == "operational"
    assert body["tenants"]["total"] == 2
    assert body["tenants"]["active"] == 2
    assert body["domains"] >= 2
    assert set(body["builds"]) == {"queued", "building", "failed", "completed"}

    support = local_env.client.post(
        f"/api/v1/platform/tenants/{local_env.alpha_tenant['id']}/support-sessions",
        headers=local_env.platform_headers(),
        json={"reason": "Auditoria operacional autorizada", "ticket": "SUP-2026-0001", "minutes": 15},
    )
    assert support.status_code == 201, support.text
    assert support.json()["banner_required"] is True

    listed = local_env.client.get(
        "/api/v1/platform/support-sessions",
        headers=local_env.platform_headers(),
        params={"tenant_id": local_env.alpha_tenant["id"], "active_only": True},
    )
    assert listed.status_code == 200, listed.text
    assert [row["id"] for row in listed.json()["items"]] == [support.json()["id"]]

    audit = local_env.client.get(
        "/api/v1/platform/audit",
        headers=local_env.platform_headers(),
        params={"tenant_id": local_env.alpha_tenant["id"]},
    )
    assert audit.status_code == 200, audit.text
    actions = {row["action"] for row in audit.json()["items"]}
    assert "provision" in actions
    assert "support_session_started" in actions


def test_tenant_identity_cannot_enter_control_plane(local_env):
    response = local_env.client.get(
        "/api/v1/platform/status",
        headers={"host": ALPHA_HOST, "Authorization": f"Bearer {local_env.alpha_token}"},
    )
    assert response.status_code in {403, 404}, response.text

    # Um token tenant também não pode ser reaproveitado no hostname global.
    response = local_env.client.get(
        "/api/v1/platform/status",
        headers={"host": PLATFORM_HOST, "Authorization": f"Bearer {local_env.alpha_token}"},
    )
    assert response.status_code in {401, 403, 404}, response.text
