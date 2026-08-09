from __future__ import annotations


def _post(env, path: str, payload: dict, *, key: str | None = None, expected: int = 201):
    headers = env.alpha_headers(**({"Idempotency-Key": key} if key else {}))
    response = env.client.post(path, headers=headers, json=payload)
    assert response.status_code == expected, response.text
    return response.json()


def test_purchase_receipt_updates_stock_and_sale_emits_fiscal_request(local_env):
    product = _post(
        local_env,
        "/api/v1/products",
        {"sku": "KIT-001", "name": "Kit escolar", "cost": "40.00", "sale_price": "75.00"},
    )
    supplier = _post(
        local_env,
        "/api/v1/suppliers",
        {"legal_name": "Fornecedor Escolar Ltda", "cnpj": "12345678000190"},
    )
    order = _post(
        local_env,
        "/api/v1/purchase-orders",
        {
            "supplier_id": supplier["id"],
            "order_number": "PC-2026-001",
            "items": [{"product_id": product["id"], "quantity": "5", "unit_cost": "40.00"}],
        },
    )
    received = _post(
        local_env,
        f"/api/v1/purchase-orders/{order['id']}/receive",
        {"reason": "Recebimento conferido"},
        expected=200,
    )
    assert received["state"] == "received"

    products = local_env.client.get("/api/v1/products", headers=local_env.alpha_headers())
    assert products.status_code == 200, products.text
    saved = next(item for item in products.json()["items"] if item["id"] == product["id"])
    assert float(saved["stock_quantity"]) == 5.0

    cash = _post(
        local_env,
        "/api/v1/pos/cash-sessions/open",
        {"terminal_code": "PDV-TEST", "opening_amount": "0.00"},
    )
    sale = _post(
        local_env,
        "/api/v1/sales",
        {
            "cash_session_id": cash["id"],
            "channel": "pos",
            "items": [{"product_id": product["id"], "quantity": "1", "discount": "0"}],
            "payments": [{"method": "cash", "amount": "75.00"}],
            "request_fiscal_document": True,
        },
        key="sale-procurement-test",
    )
    assert sale["state"] == "completed"
    assert sale["fiscal_document_id"]

    tenant_id = local_env.alpha_tenant["id"]
    store = local_env.client.app.state.data_router.tenant_store(tenant_id)
    outbox = store.fetch_all(
        "SELECT event_type,aggregate_id FROM outbox_events WHERE tenant_id=? AND aggregate_id=? ORDER BY created_at",
        (tenant_id, sale["fiscal_document_id"]),
    )
    assert [row["event_type"] for row in outbox] == ["FiscalDocumentRequested"]

    products_after = local_env.client.get("/api/v1/products", headers=local_env.alpha_headers()).json()["items"]
    saved_after = next(item for item in products_after if item["id"] == product["id"])
    assert float(saved_after["stock_quantity"]) == 4.0


def test_purchase_order_rejects_foreign_product(local_env):
    supplier = _post(local_env, "/api/v1/suppliers", {"legal_name": "Fornecedor Alpha"})
    beta_product = local_env.client.post(
        "/api/v1/products",
        headers=local_env.beta_headers(),
        json={"sku": "BETA-001", "name": "Produto Beta", "cost": "10.00", "sale_price": "20.00"},
    )
    assert beta_product.status_code == 201, beta_product.text
    denied = local_env.client.post(
        "/api/v1/purchase-orders",
        headers=local_env.alpha_headers(),
        json={
            "supplier_id": supplier["id"],
            "order_number": "PC-CROSS",
            "items": [{"product_id": beta_product.json()["id"], "quantity": "1", "unit_cost": "10.00"}],
        },
    )
    assert denied.status_code == 404


def test_partial_receipt_transfer_inventory_return_cash_and_asset_lifecycle(local_env):
    product=_post(local_env,"/api/v1/products",{"sku":"ADV-001","name":"Material avançado","cost":"40.00","sale_price":"75.00"})
    supplier=_post(local_env,"/api/v1/suppliers",{"legal_name":"Fornecedor Avançado Ltda","cnpj":"99887766000155"})
    order=_post(local_env,"/api/v1/purchase-orders",{"supplier_id":supplier["id"],"order_number":"PC-ADV-001","items":[{"product_id":product["id"],"quantity":"10","unit_cost":"40.00"}]})
    listed=local_env.client.get("/api/v1/purchase-orders",headers=local_env.alpha_headers())
    assert listed.status_code==200,listed.text
    order_row=next(item for item in listed.json()["items"] if item["id"]==order["id"])
    order_item=order_row["items"][0]
    partial=_post(local_env,f"/api/v1/purchase-orders/{order['id']}/receive",{"reason":"Primeiro lote conferido","items":[{"purchase_order_item_id":order_item["id"],"quantity":"4"}]},expected=200)
    assert partial["state"]=="partially_received"

    transfer=_post(local_env,"/api/v1/inventory/transfers",{"from_warehouse":"default","to_warehouse":"canteen","reason":"Reposição da cantina","items":[{"product_id":product["id"],"quantity":"1"}]},key="stock-transfer-adv-001")
    assert transfer["state"]=="completed"
    count=_post(local_env,"/api/v1/inventory/counts",{"warehouse":"canteen","items":[{"product_id":product["id"],"counted_quantity":"2"}]})
    finalized=_post(local_env,f"/api/v1/inventory/counts/{count['id']}/finalize",{"reason":"Contagem física dupla"},expected=200)
    assert finalized["adjustments"]==1

    cash=_post(local_env,"/api/v1/pos/cash-sessions/open",{"terminal_code":"PDV-ADV","opening_amount":"100.00"})
    supply=_post(local_env,f"/api/v1/pos/cash-sessions/{cash['id']}/movements",{"movement_type":"supply","amount":"50.00","reason":"Troco adicional"})
    assert supply["amount"]=="50.00"
    sale=_post(local_env,"/api/v1/sales",{"cash_session_id":cash["id"],"channel":"pos","items":[{"product_id":product["id"],"quantity":"1","discount":"0"}],"payments":[{"method":"cash","amount":"75.00"}],"request_fiscal_document":False},key="sale-adv-001")
    details=local_env.client.get(f"/api/v1/sales/{sale['id']}",headers=local_env.alpha_headers())
    assert details.status_code==200,details.text
    return_data=_post(local_env,f"/api/v1/sales/{sale['id']}/returns",{"items":[{"sale_item_id":details.json()["items"][0]["id"],"quantity":"1"}],"refund_method":"cash","reason":"Produto devolvido sem uso"},key="return-adv-001")
    assert return_data["sale_state"]=="returned" and return_data["refund_state"]=="completed"
    cash_summary=local_env.client.get(f"/api/v1/pos/cash-sessions/{cash['id']}/summary",headers=local_env.alpha_headers())
    assert cash_summary.status_code==200,cash_summary.text
    assert cash_summary.json()["expected_amount"]=="150.00"
    closed=_post(local_env,f"/api/v1/pos/cash-sessions/{cash['id']}/close",{"closing_amount":"150.00","reason":"Conferência sem divergência"},expected=200)
    assert closed["difference"]=="0.00"

    second=_post(local_env,f"/api/v1/purchase-orders/{order['id']}/receive",{"reason":"Segundo lote conferido","items":[{"purchase_order_item_id":order_item["id"],"quantity":"6"}]},expected=200)
    assert second["state"]=="received"

    person=_post(local_env,"/api/v1/people",{"full_name":"Responsável Patrimonial","cpf":"72727272727"},key="asset-person-001")
    asset=_post(local_env,"/api/v1/assets",{"asset_number":"PAT-ADV-001","description":"Projetor multimídia","acquisition_cost":"3500.00","location":"Sala 01","responsible_person_id":person["id"]})
    moved=_post(local_env,f"/api/v1/assets/{asset['id']}/events",{"event_type":"move","to_location":"Laboratório 02","notes":"Mudança de sala"})
    assert moved["location"]=="Laboratório 02"
    maintenance=_post(local_env,f"/api/v1/assets/{asset['id']}/events",{"event_type":"maintenance_open","cost":"250.00","notes":"Troca preventiva da lâmpada"})
    assert maintenance["state"]=="maintenance"
    completed=_post(local_env,f"/api/v1/assets/{asset['id']}/events",{"event_type":"maintenance_complete","notes":"Equipamento revisado"})
    assert completed["state"]=="active"
    asset_details=local_env.client.get(f"/api/v1/assets/{asset['id']}",headers=local_env.alpha_headers())
    assert asset_details.status_code==200,asset_details.text
    assert len(asset_details.json()["events"])==3


def test_reserved_stock_is_preserved_during_sale_and_transfer(local_env):
    product = _post(
        local_env,
        "/api/v1/products",
        {"sku": "RES-001", "name": "Produto com reserva", "cost": "10.00", "sale_price": "20.00"},
    )
    _post(
        local_env,
        f"/api/v1/products/{product['id']}/stock-adjustments",
        {"quantity": "10", "warehouse": "default", "reason": "Carga inicial"},
        key="reserved-stock-initial",
        expected=200,
    )
    tenant_id = local_env.alpha_tenant["id"]
    store = local_env.client.app.state.data_router.tenant_store(tenant_id)
    with store.transaction() as conn:
        conn.execute(
            "UPDATE stock_balances SET reserved='4' WHERE tenant_id=? AND product_id=? AND warehouse='default'",
            (tenant_id, product["id"]),
        )

    cash = _post(
        local_env,
        "/api/v1/pos/cash-sessions/open",
        {"terminal_code": "PDV-RES", "opening_amount": "0.00"},
    )
    sale = _post(
        local_env,
        "/api/v1/sales",
        {
            "cash_session_id": cash["id"],
            "channel": "pos",
            "items": [{"product_id": product["id"], "quantity": "2", "discount": "0"}],
            "payments": [{"method": "cash", "amount": "40.00"}],
            "request_fiscal_document": False,
        },
        key="reserved-stock-sale",
    )
    assert sale["state"] == "completed"
    after_sale = store.fetch_one(
        "SELECT quantity,reserved FROM stock_balances WHERE tenant_id=? AND product_id=? AND warehouse='default'",
        (tenant_id, product["id"]),
    )
    assert float(after_sale["quantity"]) == 8.0
    assert float(after_sale["reserved"]) == 4.0

    transfer = _post(
        local_env,
        "/api/v1/inventory/transfers",
        {
            "from_warehouse": "default",
            "to_warehouse": "canteen",
            "reason": "Separação física entre depósitos",
            "items": [{"product_id": product["id"], "quantity": "2"}],
        },
        key="reserved-stock-transfer",
    )
    assert transfer["state"] == "completed"
    source = store.fetch_one(
        "SELECT quantity,reserved FROM stock_balances WHERE tenant_id=? AND product_id=? AND warehouse='default'",
        (tenant_id, product["id"]),
    )
    target = store.fetch_one(
        "SELECT quantity,reserved FROM stock_balances WHERE tenant_id=? AND product_id=? AND warehouse='canteen'",
        (tenant_id, product["id"]),
    )
    assert float(source["quantity"]) == 6.0
    assert float(source["reserved"]) == 4.0
    assert float(target["quantity"]) == 2.0
    assert float(target["reserved"]) == 0.0
