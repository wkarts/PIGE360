from __future__ import annotations


def _post(env, path: str, payload: dict, *, expected: int = 201):
    response = env.client.post(path, headers=env.alpha_headers(), json=payload)
    assert response.status_code == expected, response.text
    return response.json()


def test_school_sales_categories_are_persisted_filterable_and_tenant_scoped(local_env):
    categories = {
        "school_uniform": "FAR-001",
        "textbook": "LIV-001",
        "handout": "APS-001",
        "learning_module": "MOD-001",
        "educational_material": "MAT-001",
        "school_kit": "KIT-001",
        "event_ticket": "ING-001",
        "event": "EVE-001",
    }
    created: dict[str, dict] = {}
    for category, sku in categories.items():
        created[category] = _post(
            local_env,
            "/api/v1/products",
            {
                "sku": sku,
                "name": f"Item {category}",
                "cost": "10.00",
                "sale_price": "20.00",
                "school_catalog_category": category,
            },
        )
        assert created[category]["school_catalog_category"] == category

    for category, product in created.items():
        response = local_env.client.get(
            "/api/v1/products",
            params={"school_catalog_category": category},
            headers=local_env.alpha_headers(),
        )
        assert response.status_code == 200, response.text
        assert [row["id"] for row in response.json()["items"]] == [product["id"]]

    legacy = _post(
        local_env,
        "/api/v1/products",
        {
            "sku": "UNI-LEGACY-001",
            "name": "Uniforme legado",
            "product_type": "uniform",
            "cost": "25.00",
            "sale_price": "50.00",
        },
    )
    assert legacy["school_catalog_category"] == "school_uniform"

    beta = local_env.client.post(
        "/api/v1/products",
        headers=local_env.beta_headers(),
        json={
            "sku": "BETA-ING-001",
            "name": "Ingresso de outro tenant",
            "cost": "5.00",
            "sale_price": "15.00",
            "school_catalog_category": "event_ticket",
        },
    )
    assert beta.status_code == 201, beta.text
    listed = local_env.client.get(
        "/api/v1/products",
        params={"school_catalog_category": "event_ticket"},
        headers=local_env.alpha_headers(),
    )
    assert listed.status_code == 200, listed.text
    assert beta.json()["id"] not in {row["id"] for row in listed.json()["items"]}


def test_school_sales_categories_keep_existing_sale_flow(local_env):
    ticket = _post(
        local_env,
        "/api/v1/products",
        {
            "sku": "ING-SALE-001",
            "name": "Ingresso para feira escolar",
            "cost": "5.00",
            "sale_price": "25.00",
            "school_catalog_category": "event_ticket",
        },
    )
    adjustment = local_env.client.post(
        f"/api/v1/products/{ticket['id']}/stock-adjustments",
        headers=local_env.alpha_headers(**{"Idempotency-Key": "ticket-opening-stock-001"}),
        json={"quantity": "2", "reason": "Carga inicial de ingressos"},
    )
    assert adjustment.status_code == 200, adjustment.text
    cash = _post(
        local_env,
        "/api/v1/pos/cash-sessions/open",
        {"terminal_code": "PDV-INGRESSO", "opening_amount": "0.00"},
    )
    sale = local_env.client.post(
        "/api/v1/sales",
        headers=local_env.alpha_headers(**{"Idempotency-Key": "ticket-sale-001"}),
        json={
            "cash_session_id": cash["id"],
            "channel": "pos",
            "items": [{"product_id": ticket["id"], "quantity": "1", "discount": "0"}],
            "payments": [{"method": "cash", "amount": "25.00"}],
            "request_fiscal_document": False,
        },
    )
    assert sale.status_code == 201, sale.text
    assert sale.json()["state"] == "completed"

