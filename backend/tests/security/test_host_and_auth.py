from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from app.shared.presentation.errors import DomainError
from app.shared.security.auth import AuthService
from conftest import ALPHA_HOST, BETA_HOST, PLATFORM_HOST


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
    rotated_tokens = rotated.json()
    reused = local_env.client.post(
        "/api/v1/auth/refresh",
        headers={"host": ALPHA_HOST},
        json={"refresh_token": original},
    )
    assert reused.status_code == 401
    assert reused.json()["code"] == "INVALID_REFRESH_TOKEN"

    descendant_refresh = local_env.client.post(
        "/api/v1/auth/refresh",
        headers={"host": ALPHA_HOST},
        json={"refresh_token": rotated_tokens["refresh_token"]},
    )
    assert descendant_refresh.status_code == 401
    assert descendant_refresh.json()["code"] == "INVALID_REFRESH_TOKEN"

    descendant_access = local_env.client.get(
        "/api/v1/auth/me",
        headers={
            "host": ALPHA_HOST,
            "Authorization": f"Bearer {rotated_tokens['access_token']}",
        },
    )
    assert descendant_access.status_code == 401
    assert descendant_access.json()["code"] == "SESSION_REVOKED"


def test_concurrent_refresh_has_one_winner_and_revokes_the_replayed_family(local_env):
    login = local_env.client.post(
        "/api/v1/auth/login",
        headers={"host": ALPHA_HOST},
        json={"email": "owner@alpha.example.com", "password": "Senha-Forte-Local-2026!"},
    )
    assert login.status_code == 200
    original = login.json()["refresh_token"]
    store = local_env.client.app.state.data_router.tenant_store(local_env.alpha_tenant["id"])
    settings = local_env.client.app.state.settings

    def rotate():
        service = AuthService(
            store,
            settings,
            tenant_id=local_env.alpha_tenant["id"],
            plane="tenant",
        )
        try:
            return service.rotate_refresh(original)
        except DomainError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _: rotate(), range(2)))

    winners = [item for item in outcomes if isinstance(item, dict)]
    assert len(winners) == 1
    assert outcomes.count("INVALID_REFRESH_TOKEN") == 1

    winner = winners[0]
    descendant_refresh = local_env.client.post(
        "/api/v1/auth/refresh",
        headers={"host": ALPHA_HOST},
        json={"refresh_token": winner["refresh_token"]},
    )
    assert descendant_refresh.status_code == 401
    descendant_access = local_env.client.get(
        "/api/v1/auth/me",
        headers={"host": ALPHA_HOST, "Authorization": f"Bearer {winner['access_token']}"},
    )
    assert descendant_access.status_code == 401
    assert descendant_access.json()["code"] == "SESSION_REVOKED"


def test_logout_revokes_only_the_current_server_side_session(local_env):
    login = local_env.client.post(
        "/api/v1/auth/login",
        headers={"host": ALPHA_HOST},
        json={"email": "owner@alpha.example.com", "password": "Senha-Forte-Local-2026!"},
    )
    assert login.status_code == 200
    tokens = login.json()
    headers = {
        "host": ALPHA_HOST,
        "Authorization": f"Bearer {tokens['access_token']}",
    }

    logout = local_env.client.post(
        "/api/v1/auth/logout",
        headers=headers,
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert logout.status_code == 204
    assert logout.content == b""

    revoked_access = local_env.client.get("/api/v1/auth/me", headers=headers)
    assert revoked_access.status_code == 401
    assert revoked_access.json()["code"] == "SESSION_REVOKED"

    revoked_refresh = local_env.client.post(
        "/api/v1/auth/refresh",
        headers={"host": ALPHA_HOST},
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert revoked_refresh.status_code == 401
    assert revoked_refresh.json()["code"] == "INVALID_REFRESH_TOKEN"

    # Outra sessão do mesmo usuário não é encerrada por engano.
    still_active = local_env.client.get("/api/v1/auth/me", headers=local_env.alpha_headers())
    assert still_active.status_code == 200


def test_logout_access_session_cannot_revoke_a_different_session_refresh(local_env):
    first = local_env.client.post(
        "/api/v1/auth/login",
        headers={"host": ALPHA_HOST},
        json={"email": "owner@alpha.example.com", "password": "Senha-Forte-Local-2026!"},
    ).json()
    second = local_env.client.post(
        "/api/v1/auth/login",
        headers={"host": ALPHA_HOST},
        json={"email": "owner@alpha.example.com", "password": "Senha-Forte-Local-2026!"},
    ).json()

    logout = local_env.client.post(
        "/api/v1/auth/logout",
        headers={"host": ALPHA_HOST, "Authorization": f"Bearer {first['access_token']}"},
        json={"refresh_token": second["refresh_token"]},
    )
    assert logout.status_code == 204

    first_revoked = local_env.client.get(
        "/api/v1/auth/me",
        headers={"host": ALPHA_HOST, "Authorization": f"Bearer {first['access_token']}"},
    )
    assert first_revoked.status_code == 401
    second_active = local_env.client.get(
        "/api/v1/auth/me",
        headers={"host": ALPHA_HOST, "Authorization": f"Bearer {second['access_token']}"},
    )
    assert second_active.status_code == 200


def test_platform_logout_revokes_session_with_null_tenant_scope(local_env):
    login = local_env.client.post(
        "/api/v1/auth/login",
        headers={"host": PLATFORM_HOST},
        json={"email": "root@platform.example.com", "password": "Senha-Forte-Local-2026!"},
    )
    assert login.status_code == 200
    tokens = login.json()
    headers = {
        "host": PLATFORM_HOST,
        "Authorization": f"Bearer {tokens['access_token']}",
    }

    logout = local_env.client.post(
        "/api/v1/auth/logout",
        headers=headers,
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert logout.status_code == 204
    revoked = local_env.client.get("/api/v1/auth/me", headers=headers)
    assert revoked.status_code == 401
    assert revoked.json()["code"] == "SESSION_REVOKED"


def test_login_lockout_is_persistent_and_does_not_store_plain_email(local_env):
    email = "locked.user@alpha.example.com"
    local_env.create_alpha_user(email, ["employee"])
    settings = local_env.client.app.state.settings

    first_failure = local_env.client.post(
        "/api/v1/auth/login",
        headers={"host": ALPHA_HOST},
        json={"email": email, "password": "senha-incorreta"},
    )
    assert first_failure.status_code == 401
    reset = local_env.client.post(
        "/api/v1/auth/login",
        headers={"host": ALPHA_HOST},
        json={"email": email, "password": "Senha-Forte-Local-2026!"},
    )
    assert reset.status_code == 200

    for _ in range(settings.login_max_attempts - 1):
        denied = local_env.client.post(
            "/api/v1/auth/login",
            headers={"host": ALPHA_HOST},
            json={"email": email, "password": "senha-incorreta"},
        )
        assert denied.status_code == 401
        assert denied.json()["code"] == "INVALID_CREDENTIALS"

    limited = local_env.client.post(
        "/api/v1/auth/login",
        headers={"host": ALPHA_HOST},
        json={"email": email, "password": "senha-incorreta"},
    )
    assert limited.status_code == 429
    assert limited.json()["code"] == "LOGIN_RATE_LIMITED"
    assert int(limited.headers["Retry-After"]) > 0

    correct_password_is_still_limited = local_env.client.post(
        "/api/v1/auth/login",
        headers={"host": ALPHA_HOST},
        json={"email": email, "password": "Senha-Forte-Local-2026!"},
    )
    assert correct_password_is_still_limited.status_code == 429

    store = local_env.client.app.state.data_router.tenant_store(local_env.alpha_tenant["id"])
    rows = store.fetch_all("SELECT * FROM auth_login_attempts")
    locked = next(item for item in rows if item["failed_attempts"] == settings.login_max_attempts)
    assert len(locked["identifier_hash"]) == 64
    assert email not in repr(locked)
    assert locked["locked_until"]
