from __future__ import annotations


def _post(env, path: str, payload: dict, *, key: str | None = None, expected: int = 201):
    headers = env.alpha_headers(**({"Idempotency-Key": key} if key else {}))
    response = env.client.post(path, headers=headers, json=payload)
    assert response.status_code == expected, response.text
    return response.json()


def test_recurring_service_competence_billing_execution_and_tenant_isolation(local_env):
    person = _post(
        local_env,
        "/api/v1/people",
        {"full_name": "Responsável Serviços Verticais", "email": "servicos@alpha.example.com"},
        key="person-services-vertical-001",
    )

    catalog_payload = {
        "code": "EDUCACIONAL-2026",
        "name": "Catálogo educacional 2026",
        "description": "Serviços educacionais recorrentes e avulsos.",
        "valid_from": "2026-01-01",
        "status": "active",
    }
    catalog = _post(
        local_env,
        "/api/v1/service-catalogs",
        catalog_payload,
        key="service-catalog-vertical-001",
    )
    replay = _post(
        local_env,
        "/api/v1/service-catalogs",
        catalog_payload,
        key="service-catalog-vertical-001",
    )
    assert replay["id"] == catalog["id"]

    created_service = _post(
        local_env,
        "/api/v1/services",
        {
            "catalog_id": catalog["id"],
            "code": "MENSALIDADE-ROB-2026",
            "name": "Mensalidade de Robótica",
            "description": "Mensalidade recorrente para atividade extracurricular.",
            "service_type": "extracurricular",
            "recurrence_type": "monthly",
            "unit_of_measure": "month",
            "taxable": True,
            "status": "active",
        },
        key="service-vertical-001",
    )

    variant = _post(
        local_env,
        f"/api/v1/services/{created_service['id']}/variants",
        {
            "code": "TURMA-A",
            "name": "Turma A",
            "duration_minutes": 480,
            "capacity": 20,
            "status": "active",
        },
        key="service-variant-vertical-001",
    )

    _post(
        local_env,
        f"/api/v1/services/{created_service['id']}/price-tables",
        {
            "variant_id": variant["id"],
            "name": "Tabela 2026",
            "valid_from": "2026-01-01",
            "amount": "250.00",
            "billing_frequency": "monthly",
            "status": "active",
        },
        key="service-price-vertical-001",
    )

    fiscal = _post(
        local_env,
        f"/api/v1/services/{created_service['id']}/fiscal-profiles",
        {
            "variant_id": variant["id"],
            "valid_from": "2026-01-01",
            "nbs_code": "1.0901.10.00",
            "lc116_code": "08.02",
            "municipal_service_code": "0802",
            "cnae_code": "8599604",
            "iss_rate": "5.000000",
            "ibs_rate": "0.100000",
            "cbs_rate": "0.900000",
            "cclass_trib": "000001",
            "fiscal_trigger": "competence",
        },
        key="service-fiscal-vertical-001",
    )
    published = _post(
        local_env,
        f"/api/v1/service-fiscal-profiles/{fiscal['id']}/publish",
        {"notes": "Classificação conferida para o cenário local."},
        expected=200,
    )
    assert published["status"] == "published"
    assert published["classification_status"] == "complete"

    billing_rule = _post(
        local_env,
        f"/api/v1/services/{created_service['id']}/billing-rules",
        {
            "variant_id": variant["id"],
            "code": "MENSAL-DIA-10",
            "name": "Mensal com vencimento no dia 10",
            "billing_trigger": "competence",
            "due_day": 10,
            "installment_count": 1,
            "interval_months": 1,
            "recognition_policy": "competence",
            "fiscal_trigger": "competence",
            "status": "active",
        },
        key="service-billing-rule-vertical-001",
    )

    subscription = _post(
        local_env,
        "/api/v1/service-subscriptions",
        {
            "subscription_number": "ASS-ROB-2026-0001",
            "service_id": created_service["id"],
            "variant_id": variant["id"],
            "subscriber_person_id": person["id"],
            "billing_rule_id": billing_rule["id"],
            "starts_on": "2026-01-01",
            "quantity": "1.0000",
            "discount_amount": "20.00",
            "auto_renew": True,
        },
        key="service-subscription-vertical-001",
    )
    assert subscription["cycle_amount"] == "230.00"

    activated = _post(
        local_env,
        f"/api/v1/service-subscriptions/{subscription['id']}/activate",
        {"reason": "Contrato e autorização validados."},
        expected=200,
    )
    assert activated["status"] == "active"

    competence_payload = {"competence_key": "2026-08", "due_date": "2026-08-10"}
    competence = _post(
        local_env,
        f"/api/v1/service-subscriptions/{subscription['id']}/competencies",
        competence_payload,
        key="service-competence-vertical-2026-08",
    )
    competence_replay = _post(
        local_env,
        f"/api/v1/service-subscriptions/{subscription['id']}/competencies",
        competence_payload,
        key="service-competence-vertical-2026-08",
    )
    assert competence_replay["id"] == competence["id"]
    assert competence["status"] == "billed"
    order = competence["order"]
    assert order["status"] == "confirmed"
    assert order["total_amount"] in ("230.00", 230, 230.0)
    assert order["charge"]["state"] == "open"
    assert order["fiscal_status"] == "not_configured"
    assert order["fiscal_events"][0]["failure_code"] == "FISCAL_PROVIDER_NOT_CONFIGURED"
    assert order["executions"][0]["status"] == "scheduled"

    start_order = _post(
        local_env,
        f"/api/v1/service-orders/{order['id']}/start",
        {},
        expected=200,
    )
    assert start_order["status"] == "in_progress"

    execution_id = order["executions"][0]["id"]
    started_execution = _post(
        local_env,
        f"/api/v1/service-executions/{execution_id}/start",
        {"notes": "Execução iniciada."},
        expected=200,
    )
    assert started_execution["status"] == "in_progress"

    completed_execution = _post(
        local_env,
        f"/api/v1/service-executions/{execution_id}/complete",
        {"completed_quantity": "1.0000", "notes": "Atividade concluída.", "evidence": {"local": True}},
        expected=200,
    )
    assert completed_execution["status"] == "completed"

    completed_order = _post(
        local_env,
        f"/api/v1/service-orders/{order['id']}/complete",
        {},
        expected=200,
    )
    assert completed_order["status"] == "completed"

    dashboard = local_env.client.get("/api/v1/services-dashboard", headers=local_env.alpha_headers())
    assert dashboard.status_code == 200, dashboard.text
    assert dashboard.json()["active_subscriptions"] == 1
    assert dashboard.json()["not_configured_fiscal_events"] == 1
    assert dashboard.json()["billed_total"] in ("230.00", 230, 230.0)

    cross_tenant = local_env.client.get(
        f"/api/v1/services/{created_service['id']}",
        headers=local_env.beta_headers(),
    )
    assert cross_tenant.status_code == 404, cross_tenant.text
    assert cross_tenant.json()["code"] == "SERVICE_NOT_FOUND"
