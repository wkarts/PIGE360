from __future__ import annotations

import json


def _set_quotas(local_env, **quotas: int) -> None:
    local_env.client.app.state.data_router.control.execute(
        "UPDATE platform_tenants SET quotas_json=? WHERE id=?",
        (json.dumps(quotas), local_env.alpha_tenant["id"]),
    )


def _post(local_env, path: str, payload: dict, *, idempotency_key: str | None = None):
    extra = {"Idempotency-Key": idempotency_key} if idempotency_key else {}
    return local_env.client.post(path, headers=local_env.alpha_headers(**extra), json=payload)


def test_active_student_quota_blocks_direct_student_creation(local_env):
    _set_quotas(local_env, max_students=1)
    people = []
    for index in (1, 2):
        response = _post(
            local_env,
            "/api/v1/people",
            {"full_name": f"Aluno Quota {index}"},
            idempotency_key=f"person-student-quota-{index}",
        )
        assert response.status_code == 201, response.text
        people.append(response.json())

    first = _post(
        local_env,
        "/api/v1/students",
        {"person_id": people[0]["id"], "registration_number": "Q-001"},
    )
    assert first.status_code == 201, first.text

    blocked = _post(
        local_env,
        "/api/v1/students",
        {"person_id": people[1]["id"], "registration_number": "Q-002"},
    )
    assert blocked.status_code == 409, blocked.text
    assert blocked.json()["code"] == "TENANT_QUOTA_EXCEEDED"


def test_active_student_quota_also_blocks_candidate_conversion(local_env):
    _set_quotas(local_env, max_students=0)
    institution = _post(
        local_env,
        "/api/v1/institutions",
        {"legal_name": "Instituição Quota Ltda.", "trade_name": "Quota"},
    ).json()
    unit = _post(
        local_env,
        "/api/v1/units",
        {"institution_id": institution["id"], "code": "UQ", "name": "Unidade Quota"},
    ).json()
    year = _post(
        local_env,
        "/api/v1/academic-years",
        {
            "institution_id": institution["id"],
            "name": "2026",
            "starts_on": "2026-01-01",
            "ends_on": "2026-12-31",
        },
    ).json()
    program = _post(
        local_env,
        "/api/v1/programs",
        {
            "institution_id": institution["id"],
            "code": "PQ",
            "name": "Programa Quota",
            "education_level": "basic",
        },
    ).json()
    curriculum = _post(
        local_env,
        "/api/v1/curricula",
        {
            "program_id": program["id"],
            "code": "CQ",
            "name": "Currículo Quota",
            "effective_from": "2026-01-01",
        },
    ).json()
    person = _post(
        local_env,
        "/api/v1/people",
        {"full_name": "Candidato Bloqueado"},
        idempotency_key="candidate-person-quota",
    ).json()
    candidate = _post(
        local_env,
        "/api/v1/admissions/candidates",
        {
            "person_id": person["id"],
            "program_id": program["id"],
            "academic_year_id": year["id"],
        },
    ).json()

    blocked = _post(
        local_env,
        f"/api/v1/admissions/candidates/{candidate['id']}/convert",
        {
            "registration_number": "CAND-Q-1",
            "institution_id": institution["id"],
            "unit_id": unit["id"],
            "curriculum_id": curriculum["id"],
            "enrollment_number": "ENR-Q-1",
        },
    )
    assert blocked.status_code == 409, blocked.text
    assert blocked.json()["code"] == "TENANT_QUOTA_EXCEEDED"


def test_integration_quota_covers_generic_and_fiscal_creation_paths(local_env):
    _set_quotas(local_env, max_integrations=1)
    first = _post(
        local_env,
        "/api/v1/integration-connections",
        {
            "provider": "CloudflareDnsProvider",
            "name": "Cloudflare principal",
            "environment": "homologation",
            "capabilities": ["dns"],
        },
    )
    assert first.status_code == 201, first.text

    fiscal_payload = {
        "provider_code": "NationalNfseProvider",
        "display_name": "NFS-e nacional",
        "document_type": "NFS-e",
        "environment": "homologation",
        "capabilities": ["issue", "query"],
        "enabled": False,
    }
    blocked_fiscal = _post(
        local_env,
        "/api/v1/fiscal/providers",
        fiscal_payload,
        idempotency_key="fiscal-provider-quota-blocked",
    )
    assert blocked_fiscal.status_code == 409, blocked_fiscal.text
    assert blocked_fiscal.json()["code"] == "TENANT_QUOTA_EXCEEDED"

    archived = local_env.client.patch(
        f"/api/v1/integration-connections/{first.json()['id']}",
        headers=local_env.alpha_headers(),
        json={"state": "archived"},
    )
    assert archived.status_code == 200, archived.text

    fiscal = _post(
        local_env,
        "/api/v1/fiscal/providers",
        fiscal_payload,
        idempotency_key="fiscal-provider-quota-allowed",
    )
    assert fiscal.status_code == 201, fiscal.text

    blocked_generic = _post(
        local_env,
        "/api/v1/integration-connections",
        {
            "provider": "EvolutionApiProvider",
            "name": "Evolution secundária",
            "environment": "homologation",
            "capabilities": ["messages"],
        },
    )
    assert blocked_generic.status_code == 409, blocked_generic.text
    assert blocked_generic.json()["code"] == "TENANT_QUOTA_EXCEEDED"


def test_integration_quota_blocks_archived_reactivation_and_implicit_test(local_env):
    _set_quotas(local_env, max_integrations=1)
    archived_connection = _post(
        local_env,
        "/api/v1/integration-connections",
        {
            "provider": "CloudflareDnsProvider",
            "name": "Integração arquivada",
            "environment": "homologation",
            "capabilities": ["dns"],
        },
    )
    assert archived_connection.status_code == 201, archived_connection.text
    connection_id = archived_connection.json()["id"]
    archived = local_env.client.patch(
        f"/api/v1/integration-connections/{connection_id}",
        headers=local_env.alpha_headers(),
        json={"state": "archived"},
    )
    assert archived.status_code == 200, archived.text

    occupying = _post(
        local_env,
        "/api/v1/integration-connections",
        {
            "provider": "ConnectApiProvider",
            "name": "Integração ocupante",
            "environment": "homologation",
            "capabilities": ["messages"],
        },
    )
    assert occupying.status_code == 201, occupying.text

    blocked = local_env.client.patch(
        f"/api/v1/integration-connections/{connection_id}",
        headers=local_env.alpha_headers(),
        json={"state": "configured"},
    )
    assert blocked.status_code == 409, blocked.text
    assert blocked.json()["code"] == "TENANT_QUOTA_EXCEEDED"

    implicit = local_env.client.post(
        f"/api/v1/integration-connections/{connection_id}/test",
        headers=local_env.alpha_headers(),
    )
    assert implicit.status_code == 409, implicit.text
    assert implicit.json()["code"] == "INTEGRATION_CONNECTION_INACTIVE"

    released = local_env.client.patch(
        f"/api/v1/integration-connections/{occupying.json()['id']}",
        headers=local_env.alpha_headers(),
        json={"state": "archived"},
    )
    assert released.status_code == 200, released.text
    allowed = local_env.client.patch(
        f"/api/v1/integration-connections/{connection_id}",
        headers=local_env.alpha_headers(),
        json={"state": "configured"},
    )
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["state"] == "not_configured"


def test_integration_quota_blocks_fiscal_configuration_reactivation(local_env):
    _set_quotas(local_env, max_integrations=1)
    fiscal = _post(
        local_env,
        "/api/v1/fiscal/providers",
        {
            "provider_code": "NationalNfseProvider",
            "display_name": "NFS-e para reativação",
            "document_type": "NFS-e",
            "environment": "homologation",
            "capabilities": ["issue", "query"],
            "enabled": False,
        },
        idempotency_key="fiscal-provider-reactivation",
    )
    assert fiscal.status_code == 201, fiscal.text
    fiscal_id = fiscal.json()["id"]
    archived = local_env.client.patch(
        f"/api/v1/integration-connections/{fiscal_id}",
        headers=local_env.alpha_headers(),
        json={"state": "archived"},
    )
    assert archived.status_code == 200, archived.text

    occupying = _post(
        local_env,
        "/api/v1/integration-connections",
        {
            "provider": "CloudflareDnsProvider",
            "name": "Integração ocupante fiscal",
            "environment": "homologation",
            "capabilities": ["dns"],
        },
    )
    assert occupying.status_code == 201, occupying.text
    blocked = local_env.client.patch(
        f"/api/v1/fiscal/providers/{fiscal_id}",
        headers=local_env.alpha_headers(),
        json={"expected_version": 1, "display_name": "NFS-e bloqueada"},
    )
    assert blocked.status_code == 409, blocked.text
    assert blocked.json()["code"] == "TENANT_QUOTA_EXCEEDED"

    released = local_env.client.patch(
        f"/api/v1/integration-connections/{occupying.json()['id']}",
        headers=local_env.alpha_headers(),
        json={"state": "archived"},
    )
    assert released.status_code == 200, released.text
    allowed = local_env.client.patch(
        f"/api/v1/fiscal/providers/{fiscal_id}",
        headers=local_env.alpha_headers(),
        json={"expected_version": 1, "display_name": "NFS-e reativada"},
    )
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["version"] == 2
    stale = local_env.client.patch(
        f"/api/v1/fiscal/providers/{fiscal_id}",
        headers=local_env.alpha_headers(),
        json={"expected_version": 1, "display_name": "NFS-e atualização obsoleta"},
    )
    assert stale.status_code == 409, stale.text
    assert stale.json()["code"] == "VERSION_CONFLICT"
