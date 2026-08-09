from __future__ import annotations


def post(env, path: str, payload: dict, *, key: str | None = None, expected: int = 201):
    headers = env.alpha_headers(**({"Idempotency-Key": key} if key else {}))
    response = env.client.post(path, headers=headers, json=payload)
    assert response.status_code == expected, f"{path}: {response.status_code} {response.text}"
    return response.json()


def school_student(env):
    inst = post(env, "/api/v1/institutions", {"legal_name": "Escola Cantina Ltda", "trade_name": "Escola Cantina"})
    unit = post(env, "/api/v1/units", {"institution_id": inst["id"], "code": "MATRIZ", "name": "Matriz", "timezone": "America/Bahia"})
    year = post(env, "/api/v1/academic-years", {"institution_id": inst["id"], "name": "2026", "starts_on": "2026-01-20", "ends_on": "2026-12-18"})
    program = post(env, "/api/v1/programs", {"institution_id": inst["id"], "code": "EF2", "name": "Fundamental II", "education_level": "fundamental", "modality": "presencial"})
    curriculum = post(env, "/api/v1/curricula", {"program_id": program["id"], "code": "CURR-CANT", "name": "Currículo Cantina", "effective_from": "2026-01-01"})
    group = post(env, "/api/v1/class-groups", {"unit_id": unit["id"], "academic_year_id": year["id"], "program_id": program["id"], "curriculum_id": curriculum["id"], "code": "7A", "name": "7º A", "capacity": 30})
    person = post(env, "/api/v1/people", {"full_name": "Aluno Cantina", "cpf": "45454545454"}, key="canteen-student-person")
    student = post(env, "/api/v1/students", {"person_id": person["id"], "registration_number": "CANT-001"})
    enrollment = post(env, "/api/v1/enrollments", {"student_id": student["id"], "institution_id": inst["id"], "unit_id": unit["id"], "program_id": program["id"], "curriculum_id": curriculum["id"], "academic_year_id": year["id"], "class_group_id": group["id"], "enrollment_number": "MAT-CANT-001"}, key="canteen-enrollment")
    post(env, f"/api/v1/enrollments/{enrollment['id']}/activate", {"expected_version": 1, "reason": "Matrícula ativa para cantina"}, expected=200)
    return unit, student


def test_canteen_wallet_policy_subsidy_limits_and_refund(local_env):
    unit, student = school_student(local_env)
    product = post(
        local_env,
        "/api/v1/products",
        {
            "sku": "CANT-SAND-001",
            "name": "Sanduíche integral",
            "product_type": "food",
            "cost": "4.00",
            "sale_price": "10.00",
            "allergens": ["amendoim"],
        },
    )
    post(local_env, f"/api/v1/products/{product['id']}/stock-adjustments", {"quantity": "10", "warehouse": "default", "reason": "Estoque inicial da cantina"}, key="canteen-stock", expected=200)

    location = post(local_env, "/api/v1/canteen/locations", {"unit_id": unit["id"], "code": "CANT-01", "name": "Cantina Principal"})
    menu = post(local_env, "/api/v1/canteen/menus", {"canteen_location_id": location["id"], "name": "Cardápio Regular", "starts_on": "2020-01-01", "ends_on": "2099-12-31"})
    post(local_env, f"/api/v1/canteen/menus/{menu['id']}/items", {"product_id": product["id"]})
    post(local_env, f"/api/v1/canteen/menus/{menu['id']}/state", {"state": "active", "reason": "Cardápio aprovado"}, expected=200)
    active_menu = local_env.client.get("/api/v1/canteen/menus?active_on=2026-08-08", headers=local_env.alpha_headers())
    assert active_menu.status_code == 200, active_menu.text
    assert active_menu.json()["items"][0]["items"][0]["product_id"] == product["id"]

    wallet = post(local_env, "/api/v1/canteen/wallets", {"student_id": student["id"], "daily_limit": "50.00", "weekly_limit": "100.00"})
    credit = post(local_env, f"/api/v1/canteen/wallets/{wallet['id']}/credits", {"amount": "20.00", "method": "pix", "external_reference": "RECARGA-001", "reason": "Recarga autorizada"}, key="canteen-wallet-credit")
    assert credit["balance_after"] == "20.00"

    policy = local_env.client.put(
        f"/api/v1/canteen/students/{student['id']}/policy",
        headers=local_env.alpha_headers(),
        json={"blocked_allergens": ["amendoim"], "blocked_product_ids": [], "daily_limit": "15.00", "weekly_limit": "30.00", "notes": "Restrição alimentar inicial"},
    )
    assert policy.status_code == 200, policy.text

    subsidy = post(local_env, "/api/v1/canteen/subsidies", {"student_id": student["id"], "subsidy_type": "fixed", "amount": "5.00", "valid_from": "2020-01-01", "valid_until": "2099-12-31", "reason": "Benefício institucional"})
    assert subsidy["amount"] == "5.00"

    cash = post(local_env, "/api/v1/pos/cash-sessions/open", {"terminal_code": "CANTINA-01", "opening_amount": "0.00"})
    blocked = local_env.client.post(
        "/api/v1/sales",
        headers={**local_env.alpha_headers(), "Idempotency-Key": "canteen-sale-blocked"},
        json={"cash_session_id": cash["id"], "channel": "canteen", "student_id": student["id"], "canteen_location_id": location["id"], "items": [{"product_id": product["id"], "quantity": "1", "discount": "0"}], "payments": [{"method": "wallet", "amount": "5.00"}], "request_fiscal_document": False},
    )
    assert blocked.status_code == 409, blocked.text
    assert blocked.json()["code"] == "CANTEEN_ALLERGEN_BLOCKED"

    policy2 = local_env.client.put(
        f"/api/v1/canteen/students/{student['id']}/policy",
        headers=local_env.alpha_headers(),
        json={"blocked_allergens": [], "blocked_product_ids": [], "daily_limit": "15.00", "weekly_limit": "30.00", "notes": "Restrição revisada"},
    )
    assert policy2.status_code == 200, policy2.text

    quote = local_env.client.post(
        "/api/v1/canteen/quote",
        headers=local_env.alpha_headers(),
        json={
            "canteen_location_id": location["id"],
            "student_id": student["id"],
            "items": [{"product_id": product["id"], "quantity": "1"}],
        },
    )
    assert quote.status_code == 200, quote.text
    quote_data = quote.json()
    assert quote_data["total_amount"] == "10.00"
    assert quote_data["subsidy_amount"] == "5.00"
    assert quote_data["customer_due"] == "5.00"
    assert quote_data["wallet_balance"] == "20.00"

    sale = post(
        local_env,
        "/api/v1/sales",
        {"cash_session_id": cash["id"], "channel": "canteen", "student_id": student["id"], "canteen_location_id": location["id"], "items": [{"product_id": product["id"], "quantity": "1", "discount": "0"}], "payments": [{"method": "wallet", "amount": "5.00"}], "request_fiscal_document": False},
        key="canteen-sale-001",
    )
    assert sale["total_amount"] == "10.00"
    assert sale["subsidy_amount"] == "5.00"
    assert sale["customer_due"] == "5.00"

    wallets = local_env.client.get(f"/api/v1/canteen/wallets?student_id={student['id']}", headers=local_env.alpha_headers())
    assert wallets.status_code == 200, wallets.text
    assert float(wallets.json()["items"][0]["balance"]) == 15.0

    limited = local_env.client.post(
        "/api/v1/sales",
        headers={**local_env.alpha_headers(), "Idempotency-Key": "canteen-sale-limit"},
        json={"cash_session_id": cash["id"], "channel": "canteen", "student_id": student["id"], "canteen_location_id": location["id"], "items": [{"product_id": product["id"], "quantity": "1", "discount": "0"}], "payments": [{"method": "wallet", "amount": "5.00"}], "request_fiscal_document": False},
    )
    assert limited.status_code == 409, limited.text
    assert limited.json()["code"] == "CANTEEN_DAILY_LIMIT_EXCEEDED"

    details = local_env.client.get(f"/api/v1/sales/{sale['id']}", headers=local_env.alpha_headers())
    assert details.status_code == 200, details.text
    payments = {row["method"]: float(row["amount"]) for row in details.json()["payments"]}
    assert payments == {"wallet": 5.0, "institutional_credit": 5.0}
    sale_item_id = details.json()["items"][0]["id"]

    returned = post(
        local_env,
        f"/api/v1/sales/{sale['id']}/returns",
        {"items": [{"sale_item_id": sale_item_id, "quantity": "1"}], "refund_method": "wallet", "reason": "Devolução da refeição"},
        key="canteen-return-001",
    )
    assert returned["total_amount"] == "10.00"
    assert returned["refund_amount"] == "5.00"
    assert returned["subsidy_reversal_amount"] == "5.00"
    assert returned["sale_state"] == "returned"

    wallets_after = local_env.client.get(f"/api/v1/canteen/wallets?student_id={student['id']}", headers=local_env.alpha_headers())
    assert wallets_after.status_code == 200, wallets_after.text
    wallet_after = wallets_after.json()["items"][0]
    assert float(wallet_after["balance"]) == 20.0
    # A listagem administrativa é resumida; prova o detalhe diretamente no storage físico.
    tenant_id = local_env.alpha_tenant["id"]
    store = local_env.client.app.state.data_router.tenant_store(tenant_id)
    refund_tx = store.fetch_one("SELECT amount FROM wallet_transactions WHERE tenant_id=? AND wallet_id=? AND transaction_type='refund'", (tenant_id, wallet["id"]))
    assert float(refund_tx["amount"]) == 5.0
    sale_refund = store.fetch_one("SELECT amount,state FROM sale_refunds WHERE tenant_id=? AND sale_return_id=?", (tenant_id, returned["id"]))
    assert float(sale_refund["amount"]) == 5.0
    assert sale_refund["state"] == "completed"

    free_meal = post(
        local_env,
        "/api/v1/canteen/subsidies",
        {
            "student_id": student["id"],
            "subsidy_type": "free_meal",
            "valid_from": "2020-01-01",
            "valid_until": "2099-12-31",
            "reason": "Refeição integralmente subsidiada",
        },
    )
    assert free_meal["subsidy_type"] == "free_meal"
    free_quote = local_env.client.post(
        "/api/v1/canteen/quote",
        headers=local_env.alpha_headers(),
        json={
            "canteen_location_id": location["id"],
            "student_id": student["id"],
            "items": [{"product_id": product["id"], "quantity": "1"}],
        },
    )
    assert free_quote.status_code == 200, free_quote.text
    assert free_quote.json()["customer_due"] == "0.00"
    fully_subsidized = post(
        local_env,
        "/api/v1/sales",
        {
            "cash_session_id": cash["id"],
            "channel": "canteen",
            "student_id": student["id"],
            "canteen_location_id": location["id"],
            "items": [{"product_id": product["id"], "quantity": "1", "discount": "0"}],
            "payments": [],
            "request_fiscal_document": False,
        },
        key="canteen-sale-free-meal",
    )
    assert fully_subsidized["total_amount"] == "10.00"
    assert fully_subsidized["subsidy_amount"] == "10.00"
    assert fully_subsidized["customer_due"] == "0.00"
    wallet_after_free_meal = local_env.client.get(f"/api/v1/canteen/wallets?student_id={student['id']}", headers=local_env.alpha_headers())
    assert wallet_after_free_meal.status_code == 200, wallet_after_free_meal.text
    assert float(wallet_after_free_meal.json()["items"][0]["balance"]) == 20.0
