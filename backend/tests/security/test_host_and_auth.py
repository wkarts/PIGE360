from __future__ import annotations

from conftest import ALPHA_HOST, BETA_HOST


def test_unknown_host_and_public_tenant_selector_are_rejected(local_env):
    unknown = local_env.client.get("/api/v1/health/live", headers={"host": "unknown.school.local"})
    assert unknown.status_code == 404
    assert unknown.json()["code"] == "UNKNOWN_HOST"

    forbidden_header = local_env.client.get(
        "/api/v1/tenant/context",
        headers={**local_env.alpha_headers(), "X-Tenant-ID": local_env.alpha_tenant["id"]},
    )
    assert forbidden_header.status_code == 400
    assert forbidden_header.json()["code"] == "PUBLIC_TENANT_SELECTOR_FORBIDDEN"

    forbidden_query = local_env.client.get(
        "/api/v1/tenant/context?tenant_id=anything",
        headers=local_env.alpha_headers(),
    )
    assert forbidden_query.status_code == 400


def test_token_is_bound_to_plane_and_tenant(local_env):
    cross_tenant = local_env.client.get(
        "/api/v1/tenant/context",
        headers={"host": BETA_HOST, "Authorization": f"Bearer {local_env.alpha_token}"},
    )
    assert cross_tenant.status_code == 403
    assert cross_tenant.json()["code"] == "TOKEN_SCOPE_MISMATCH"

    tenant_on_platform = local_env.client.get(
        "/api/v1/auth/me",
        headers={"host": "api.platform.local", "Authorization": f"Bearer {local_env.alpha_token}"},
    )
    assert tenant_on_platform.status_code in {401, 403}

    platform_on_tenant = local_env.client.get(
        "/api/v1/auth/me",
        headers={"host": ALPHA_HOST, "Authorization": f"Bearer {local_env.platform_token}"},
    )
    assert platform_on_tenant.status_code in {401, 403}


def test_refresh_token_rotation_blocks_reuse(local_env):
    login = local_env.client.post(
        "/api/v1/auth/login",
        headers={"host": ALPHA_HOST},
        json={"email": "owner@alpha.example.com", "password": "Senha-Forte-Local-2026!"},
    )
    assert login.status_code == 200
    original = login.json()["refresh_token"]
    rotated = local_env.client.post(
        "/api/v1/auth/refresh",
        headers={"host": ALPHA_HOST},
        json={"refresh_token": original},
    )
    assert rotated.status_code == 200
    reused = local_env.client.post(
        "/api/v1/auth/refresh",
        headers={"host": ALPHA_HOST},
        json={"refresh_token": original},
    )
    assert reused.status_code == 401
    assert reused.json()["code"] == "INVALID_REFRESH_TOKEN"
