from __future__ import annotations

from app.modules.tenancy.domain_management import _cloudflare_validation_records


def test_custom_domain_requires_txt_then_requests_tls(local_env):
    tenant_id = local_env.alpha_tenant["id"]
    created = local_env.client.post(
        f"/api/v1/platform/tenants/{tenant_id}/domains",
        headers=local_env.platform_headers(),
        json={"hostname": "portal.alpha-example.com", "surface": "admin"},
    )
    assert created.status_code == 201, created.text
    domain = created.json()
    assert domain["status"] == "pending_verification"
    assert domain["verification_status"] == "pending"
    assert domain["verification_record"]["type"] == "TXT"
    assert domain["verification_record"]["name"] == "_pige360-verification.portal.alpha-example.com"
    assert domain["verification_record"]["value"].startswith("pige360=")
    assert domain["routing_record"]["type"] == "CNAME"
    assert domain["routing_record"]["name"] == "portal.alpha-example.com"
    assert domain["routing_record"]["value"] == "edge.pige360.com.br"
    assert "verification_token" not in domain

    local_env.client.app.state.domain_txt_lookup = lambda _name: {"outro-token"}
    mismatch = local_env.client.post(
        f"/api/v1/platform/tenants/{tenant_id}/domains/{domain['id']}/verify",
        headers=local_env.platform_headers(),
    )
    assert mismatch.status_code == 409, mismatch.text
    assert mismatch.json()["code"] == "DOMAIN_VERIFICATION_MISMATCH"

    token = domain["verification_record"]["value"]
    local_env.client.app.state.domain_txt_lookup = lambda _name: {token}
    verified = local_env.client.post(
        f"/api/v1/platform/tenants/{tenant_id}/domains/{domain['id']}/verify",
        headers=local_env.platform_headers(),
    )
    assert verified.status_code == 200, verified.text
    result = verified.json()
    assert result["verification_status"] == "verified"
    assert result["status"] == "pending_tls"
    assert result["provider"] == "edge_acme"
    assert result["certificate_status"] == "pending"
    assert "verification_record" not in result
    assert result["routing_record"]["value"] == "edge.pige360.com.br"

    listed = local_env.client.get(
        f"/api/v1/platform/tenants/{tenant_id}/domains",
        headers=local_env.platform_headers(),
    )
    assert listed.status_code == 200, listed.text
    assert any(item["hostname"] == "portal.alpha-example.com" for item in listed.json()["items"])

    disabled = local_env.client.delete(
        f"/api/v1/platform/tenants/{tenant_id}/domains/{domain['id']}",
        headers=local_env.platform_headers(),
    )
    assert disabled.status_code == 200, disabled.text
    assert disabled.json()["status"] == "disabled"


def test_cloudflare_saas_validation_records_are_normalized():
    records = _cloudflare_validation_records(
        {
            "ownership_verification": {
                "type": "txt",
                "name": "_cf-custom-hostname.portal.example.com",
                "value": "ownership-token",
            },
            "ssl": {
                "validation_records": [
                    {
                        "status": "pending",
                        "txt_name": "_acme-challenge.portal.example.com",
                        "txt_value": "certificate-token",
                    },
                    {
                        "status": "pending",
                        "cname": "_validation.portal.example.com",
                        "cname_target": "validation.cloudflare.example",
                    },
                ]
            },
        }
    )

    assert records == [
        {
            "purpose": "hostname_ownership",
            "type": "TXT",
            "name": "_cf-custom-hostname.portal.example.com",
            "value": "ownership-token",
        },
        {
            "purpose": "certificate_validation",
            "type": "TXT",
            "name": "_acme-challenge.portal.example.com",
            "value": "certificate-token",
            "status": "pending",
        },
        {
            "purpose": "certificate_validation",
            "type": "CNAME",
            "name": "_validation.portal.example.com",
            "value": "validation.cloudflare.example",
            "status": "pending",
        },
    ]


def test_custom_domain_cannot_claim_canonical_zone(local_env):
    response = local_env.client.post(
        f"/api/v1/platform/tenants/{local_env.alpha_tenant['id']}/domains",
        headers=local_env.platform_headers(),
        json={"hostname": "qualquer.pige360.com.br", "surface": "admin"},
    )
    assert response.status_code == 409, response.text
    assert response.json()["code"] == "CUSTOM_DOMAIN_CANONICAL_ZONE_FORBIDDEN"


def test_platform_logs_are_proxied_with_tenant_and_correlation_filters(local_env):
    captured: dict[str, object] = {}

    def fake_loki(query: str, start_ns: int, end_ns: int, limit: int):
        captured.update(query=query, start_ns=start_ns, end_ns=end_ns, limit=limit)
        return {
            "status": "success",
            "data": {
                "resultType": "streams",
                "result": [
                    {
                        "stream": {
                            "platform": "pige360",
                            "service": "pige360-api",
                            "tenant_id": local_env.alpha_tenant["id"],
                            "tenant_code": "alpha-school",
                            "plane": "tenant",
                        },
                        "values": [
                            [
                                "1788336000000000000",
                                '{"event":"http_request","level":"info","tenant_code":"alpha-school","correlation_id":"corr-123","status_code":200}',
                            ]
                        ],
                    }
                ],
            },
        }

    local_env.client.app.state.loki_query = fake_loki
    response = local_env.client.get(
        "/api/v1/platform/logs",
        headers=local_env.platform_headers(),
        params={
            "tenant_id": local_env.alpha_tenant["id"],
            "correlation_id": "corr-123",
            "service": "pige360-api",
            "minutes": 30,
            "limit": 25,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["items"][0]["event"]["correlation_id"] == "corr-123"
    assert body["items"][0]["labels"]["tenant_code"] == "alpha-school"
    query = str(captured["query"])
    assert 'platform="pige360"' in query
    assert f'tenant_id="{local_env.alpha_tenant["id"]}"' in query
    assert 'service="pige360-api"' in query
    assert 'correlation_id="corr-123"' in query
    assert captured["limit"] == 25
