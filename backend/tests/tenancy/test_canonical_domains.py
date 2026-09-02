from __future__ import annotations


PASSWORD = "Senha-Forte-Local-2026!"


def test_platform_domain_policy_exposes_canonical_wildcard(local_env):
    response = local_env.client.get(
        "/api/v1/platform/domain-policy",
        headers=local_env.platform_headers(),
    )

    assert response.status_code == 200, response.text
    policy = response.json()
    assert policy["base_domain"] == "pige360.com.br"
    assert policy["tenant_base_domain"] == "pige360.com.br"
    assert policy["canonical_pattern"] == "{slug}.pige360.com.br"
    assert policy["wildcard"] == "*.pige360.com.br"
    assert policy["dns_per_canonical_tenant_required"] is False
    assert policy["custom_domains_require_verification"] is True
    assert policy["tenant_selector"] == "hostname_only"
    assert {"api", "console", "ops", "admin", "platform"} <= set(policy["reserved_slugs"])


def test_tenant_without_hostname_receives_canonical_domain(local_env):
    response = local_env.client.post(
        "/api/v1/platform/tenants",
        headers=local_env.platform_headers(),
        json={
            "code": "colegio-modelo",
            "legal_name": "Colégio Modelo Educacional Ltda.",
            "trade_name": "Colégio Modelo",
            "owner_email": "owner@modelo.example.com",
            "owner_password": PASSWORD,
        },
    )

    assert response.status_code == 201, response.text
    tenant = response.json()
    assert tenant["hostname"] == "colegio-modelo.pige360.com.br"
    assert tenant["canonical_hostname"] == "colegio-modelo.pige360.com.br"
    assert tenant["domain_mode"] == "wildcard"

    domains_response = local_env.client.get(
        f"/api/v1/platform/tenants/{tenant['id']}/domains",
        headers=local_env.platform_headers(),
    )
    assert domains_response.status_code == 200, domains_response.text
    canonical = next(item for item in domains_response.json()["items"] if item["is_canonical"])
    assert canonical["hostname"] == "colegio-modelo.pige360.com.br"
    assert canonical["status"] == "active"
    assert canonical["certificate_policy"] == "canonical_wildcard"
    assert canonical["certificate_status"] == "active"
    assert canonical["verification_status"] == "not_required"
    assert canonical["provider"] == "platform_wildcard"

    login = local_env.client.post(
        "/api/v1/auth/login",
        headers={"host": tenant["hostname"]},
        json={"email": "owner@modelo.example.com", "password": PASSWORD},
    )
    assert login.status_code == 200, login.text


def test_reserved_platform_slug_cannot_be_provisioned(local_env):
    response = local_env.client.post(
        "/api/v1/platform/tenants",
        headers=local_env.platform_headers(),
        json={
            "code": "console",
            "legal_name": "Instituição Inválida Ltda.",
            "trade_name": "Console School",
            "owner_email": "owner@reserved.example.com",
            "owner_password": PASSWORD,
        },
    )

    assert response.status_code == 409, response.text
    assert response.json()["code"] == "TENANT_SLUG_RESERVED"
