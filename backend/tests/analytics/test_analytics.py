from __future__ import annotations


def _post(env, path: str, payload: dict, *, key: str | None = None, expected: int = 201):
    headers = env.alpha_headers(**({"Idempotency-Key": key} if key else {}))
    response = env.client.post(path, headers=headers, json=payload)
    assert response.status_code == expected, response.text
    return response.json()


def test_analytics_uses_physical_tenant_data_and_isolates_tenants(local_env):
    person = _post(local_env, "/api/v1/people", {"full_name": "Ana Analytics", "cpf": "11144477735"}, key="analytics-person")
    _post(local_env, "/api/v1/students", {"person_id": person["id"], "registration_number": "ANA-001"})
    contract = _post(local_env, "/api/v1/finance/contracts", {"description": "Contrato Analytics", "total_amount": "900.00", "competence_rule": "billing"})
    installments = _post(local_env, f"/api/v1/finance/contracts/{contract['id']}/installments", {"count": 3, "first_due_date": "2026-08-10", "interval_months": 1})
    assert len(installments["installments"]) == 3
    product = _post(local_env, "/api/v1/products", {"sku": "AN-001", "name": "Produto Analytics", "unit": "UN", "cost": "5.00", "sale_price": "10.00"})
    adjustment = local_env.client.post(
        f"/api/v1/products/{product['id']}/stock-adjustments",
        headers=local_env.alpha_headers(**{"Idempotency-Key": "analytics-stock"}),
        json={"quantity": "12", "warehouse": "default", "reason": "Carga analytics", "unit_cost": "5.00"},
    )
    assert adjustment.status_code == 200, adjustment.text

    response = local_env.client.get("/api/v1/analytics/overview?from=2026-08-01&to=2026-10-31", headers=local_env.alpha_headers())
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["academic"]["active_students"] == 1
    assert body["finance"]["open_receivables"]["count"] == 3
    assert body["finance"]["open_receivables"]["balance"] == 900.0
    assert body["operations"]["inventory"]["quantity"] == 12.0
    assert body["academic"]["attendance"]["policy_aware"] is True

    beta = local_env.client.get("/api/v1/analytics/overview?from=2026-08-01&to=2026-10-31", headers=local_env.beta_headers())
    assert beta.status_code == 200, beta.text
    assert beta.json()["academic"]["active_students"] == 0
    assert beta.json()["finance"]["open_receivables"]["count"] == 0
    assert beta.json()["operations"]["inventory"]["quantity"] == 0.0


def test_analytics_rejects_invalid_period_and_unprivileged_role(local_env):
    invalid = local_env.client.get("/api/v1/analytics/overview?from=2026-10-01&to=2026-08-01", headers=local_env.alpha_headers())
    assert invalid.status_code == 422
    assert invalid.json()["code"] == "ANALYTICS_INVALID_PERIOD"

    _, token = local_env.create_alpha_user("analytics-teacher@alpha.example.com", ["teacher"])
    denied = local_env.client.get(
        "/api/v1/analytics/overview?from=2026-08-01&to=2026-08-31",
        headers=local_env.headers("admin.alpha.school.local", token),
    )
    assert denied.status_code == 403
