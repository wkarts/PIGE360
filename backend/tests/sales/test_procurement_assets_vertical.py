from __future__ import annotations


def _post(env, path: str, payload: dict, *, key: str | None = None, expected: int = 201):
    headers = env.alpha_headers(**({"Idempotency-Key": key} if key else {}))
    response = env.client.post(path, headers=headers, json=payload)
    assert response.status_code == expected, response.text
    return response.json()


def test_procurement_inventory_lots_reservations_counts_and_assets(local_env):
    product = _post(
        local_env,
        "/api/v1/products",
        {
            "sku": "LOT-2026-001",
            "name": "Equipamento controlado por lote",
            "cost": "100.00",
            "sale_price": "180.00",
            "fiscal_profile": {"requires_lot": True},
        },
    )
    count_product = _post(
        local_env,
        "/api/v1/products",
        {
            "sku": "CNT-2026-001",
            "name": "Material de inventário",
            "cost": "15.00",
            "sale_price": "25.00",
        },
    )
    _post(
        local_env,
        f"/api/v1/products/{count_product['id']}/stock-adjustments",
        {"quantity": "5", "warehouse": "default", "reason": "Carga inicial do inventário"},
        key="inventory-count-initial-stock-001",
        expected=200,
    )

    supplier_payload = {
        "code": "FOR-EQUIP-001",
        "legal_name": "Fornecedor de Equipamentos Educacionais Ltda",
        "trade_name": "Fornecedor Equipamentos",
        "cnpj": "12345678000190",
        "email": "compras@fornecedor.example.com",
        "phone": "+5571999999999",
        "rating": "4.75",
        "payment_terms": {"days": [30, 60]},
        "contacts": [
            {
                "name": "Atendimento Comercial",
                "email": "comercial@fornecedor.example.com",
                "phone": "+5571988888888",
                "role": "commercial",
                "primary": True,
            }
        ],
    }
    supplier = _post(
        local_env,
        "/api/v1/suppliers",
        supplier_payload,
        key="supplier-vertical-001",
    )
    supplier_replay = _post(
        local_env,
        "/api/v1/suppliers",
        supplier_payload,
        key="supplier-vertical-001",
    )
    assert supplier_replay["id"] == supplier["id"]
    assert supplier["contacts"][0]["primary"] is True

    variant = _post(
        local_env,
        "/api/v1/inventory/product-variants",
        {
            "product_id": product["id"],
            "sku": "LOT-2026-001-AZ",
            "name": "Modelo azul",
            "attributes": {"color": "azul"},
            "sale_price": "185.00",
            "cost_price": "100.00",
        },
        key="product-variant-vertical-001",
    )
    barcode = _post(
        local_env,
        "/api/v1/inventory/product-barcodes",
        {
            "product_id": product["id"],
            "variant_id": variant["id"],
            "barcode": "7891234567890",
            "barcode_type": "ean13",
            "primary": True,
        },
        key="product-barcode-vertical-001",
    )
    assert barcode["variant_id"] == variant["id"]

    requisition = _post(
        local_env,
        "/api/v1/procurement/requisitions",
        {
            "needed_by": "2026-09-10",
            "justification": "Reposição de equipamentos para o laboratório.",
            "items": [
                {
                    "product_id": product["id"],
                    "quantity": "5.0000",
                    "estimated_unit_price": "100.00",
                }
            ],
        },
        key="purchase-requisition-vertical-001",
    )
    requisition_id = requisition["requisition"]["id"]
    requisition_item_id = requisition["items"][0]["id"]
    submitted = _post(
        local_env,
        f"/api/v1/procurement/requisitions/{requisition_id}/submit",
        {},
        expected=200,
    )
    assert submitted["requisition"]["status"] == "submitted"
    approved = _post(
        local_env,
        f"/api/v1/procurement/requisitions/{requisition_id}/approve",
        {
            "approved_quantities": {requisition_item_id: "5.0000"},
            "reason": "Necessidade operacional validada.",
        },
        expected=200,
    )
    assert approved["requisition"]["status"] == "approved"

    quotation = _post(
        local_env,
        "/api/v1/procurement/quotations",
        {
            "requisition_id": requisition_id,
            "response_deadline": "2026-08-20T18:00:00Z",
            "currency": "BRL",
            "supplier_ids": [supplier["id"]],
        },
        key="quotation-vertical-001",
    )
    quotation_id = quotation["quotation"]["id"]
    quotation_item_id = quotation["items"][0]["id"]
    proposal = _post(
        local_env,
        f"/api/v1/procurement/quotations/{quotation_id}/suppliers/{supplier['id']}/proposal",
        {
            "delivery_days": 5,
            "payment_terms": {"days": [30, 60]},
            "notes": "Proposta válida para a quantidade integral.",
            "items": [
                {
                    "quotation_item_id": quotation_item_id,
                    "unit_price": "98.50",
                    "quantity_available": "5.0000",
                    "brand": "EducTech",
                }
            ],
        },
        key="quotation-proposal-vertical-001",
    )
    assert proposal["supplier"]["status"] == "responded"

    awarded = _post(
        local_env,
        f"/api/v1/procurement/quotations/{quotation_id}/award",
        {
            "supplier_id": supplier["id"],
            "warehouse_id": "default",
            "expected_on": "2026-08-25",
            "reason": "Melhor combinação de preço e prazo.",
            "freight_amount": "10.00",
            "discount_amount": "2.50",
        },
        key="quotation-award-vertical-001",
    )
    order = awarded["order"]
    order_item = awarded["items"][0]
    assert order["status"] == "approved"

    # Um pedido criado diretamente começa em rascunho e não pode ser recebido.
    draft_order = _post(
        local_env,
        "/api/v1/procurement/orders",
        {
            "supplier_id": supplier["id"],
            "warehouse_id": "default",
            "items": [
                {"product_id": count_product["id"], "quantity": "1.0000", "unit_price": "15.00"}
            ],
        },
        key="draft-order-vertical-001",
    )
    denied_receipt = local_env.client.post(
        f"/api/v1/procurement/orders/{draft_order['order']['id']}/receipts",
        headers=local_env.alpha_headers(**{"Idempotency-Key": "draft-receipt-denied-001"}),
        json={
            "items": [
                {
                    "purchase_order_item_id": draft_order["items"][0]["id"],
                    "quantity": "1.0000",
                    "unit_cost": "15.0000",
                }
            ]
        },
    )
    assert denied_receipt.status_code == 409, denied_receipt.text
    assert denied_receipt.json()["code"] == "PURCHASE_ORDER_NOT_RECEIVABLE"

    missing_lot = local_env.client.post(
        f"/api/v1/procurement/orders/{order['id']}/receipts",
        headers=local_env.alpha_headers(**{"Idempotency-Key": "receipt-missing-lot-001"}),
        json={
            "items": [
                {
                    "purchase_order_item_id": order_item["id"],
                    "quantity": "2.0000",
                    "unit_cost": "98.5000",
                }
            ]
        },
    )
    assert missing_lot.status_code == 422, missing_lot.text
    assert missing_lot.json()["code"] == "INVENTORY_LOT_REQUIRED"

    partial = _post(
        local_env,
        f"/api/v1/procurement/orders/{order['id']}/receipts",
        {
            "supplier_document_number": "NF-1001",
            "notes": "Recebimento parcial conferido.",
            "items": [
                {
                    "purchase_order_item_id": order_item["id"],
                    "quantity": "2.0000",
                    "unit_cost": "98.5000",
                    "lot_number": "LOTE-EDU-2026-01",
                    "manufactured_on": "2026-07-01",
                    "expires_on": "2027-07-01",
                }
            ],
        },
        key="goods-receipt-partial-001",
    )
    assert partial["order"]["status"] == "partially_received"
    lot_id = partial["lots"][0]["id"]
    receipt_item_id = partial["items"][0]["id"]

    exceeds = local_env.client.post(
        f"/api/v1/procurement/orders/{order['id']}/receipts",
        headers=local_env.alpha_headers(**{"Idempotency-Key": "goods-receipt-exceeds-001"}),
        json={
            "items": [
                {
                    "purchase_order_item_id": order_item["id"],
                    "quantity": "4.0000",
                    "unit_cost": "98.5000",
                    "lot_number": "LOTE-EDU-2026-01",
                    "expires_on": "2027-07-01",
                }
            ]
        },
    )
    assert exceeds.status_code == 409, exceeds.text
    assert exceeds.json()["code"] == "RECEIPT_QUANTITY_EXCEEDS_REMAINING"
    order_after_failure = local_env.client.get(
        f"/api/v1/procurement/orders/{order['id']}", headers=local_env.alpha_headers()
    )
    assert order_after_failure.status_code == 200, order_after_failure.text
    assert float(order_after_failure.json()["items"][0]["received_quantity"]) == 2.0

    completed_receipt = _post(
        local_env,
        f"/api/v1/procurement/orders/{order['id']}/receipts",
        {
            "supplier_document_number": "NF-1002",
            "notes": "Recebimento final conferido.",
            "items": [
                {
                    "purchase_order_item_id": order_item["id"],
                    "quantity": "3.0000",
                    "unit_cost": "98.5000",
                    "lot_number": "LOTE-EDU-2026-01",
                    "expires_on": "2027-07-01",
                }
            ],
        },
        key="goods-receipt-final-001",
    )
    assert completed_receipt["order"]["status"] == "received"

    lots = local_env.client.get(
        f"/api/v1/inventory/lots?product_id={product['id']}&warehouse_id=default",
        headers=local_env.alpha_headers(),
    )
    assert lots.status_code == 200, lots.text
    saved_lot = lots.json()["items"][0]
    assert saved_lot["id"] == lot_id
    assert float(saved_lot["quantity"]) == 5.0

    released_reservation = _post(
        local_env,
        "/api/v1/inventory/reservations",
        {
            "product_id": product["id"],
            "warehouse_id": "default",
            "lot_id": lot_id,
            "source_type": "laboratory_request",
            "source_id": "LAB-RES-001",
            "quantity": "1.0000",
        },
        key="stock-reservation-release-001",
    )
    released = _post(
        local_env,
        f"/api/v1/inventory/reservations/{released_reservation['id']}/release",
        {},
        expected=200,
    )
    assert released["status"] == "released"

    consumed_reservation = _post(
        local_env,
        "/api/v1/inventory/reservations",
        {
            "product_id": product["id"],
            "warehouse_id": "default",
            "lot_id": lot_id,
            "source_type": "laboratory_request",
            "source_id": "LAB-RES-002",
            "quantity": "1.0000",
        },
        key="stock-reservation-consume-001",
    )
    consumed = _post(
        local_env,
        f"/api/v1/inventory/reservations/{consumed_reservation['id']}/consume",
        {},
        expected=200,
    )
    assert consumed["status"] == "consumed"
    assert consumed["stock_movement"]["quantity"] in ("-1.0000", "-1")

    inventory_count = _post(
        local_env,
        "/api/v1/inventory/counts",
        {
            "warehouse_id": "default",
            "product_ids": [count_product["id"]],
            "include_zero_balance": True,
        },
        key="advanced-inventory-count-001",
    )
    assert inventory_count["count"]["status"] == "counting"
    count_id = inventory_count["count"]["id"]
    count_item_id = inventory_count["items"][0]["id"]
    count_detail = local_env.client.get(
        f"/api/v1/inventory/counts/{count_id}", headers=local_env.alpha_headers()
    )
    assert count_detail.status_code == 200, count_detail.text
    assert float(count_detail.json()["items"][0]["expected_quantity"]) == 5.0
    count_complete = _post(
        local_env,
        f"/api/v1/inventory/counts/{count_id}/complete",
        {
            "reason": "Contagem física auditada.",
            "items": [{"item_id": count_item_id, "counted_quantity": "4.0000"}],
        },
        expected=200,
    )
    assert count_complete["count"]["status"] == "completed"
    assert len(count_complete["adjustments"]) == 1

    purchase_return = _post(
        local_env,
        f"/api/v1/procurement/orders/{order['id']}/returns",
        {
            "reason": "Unidade devolvida ao fornecedor após inspeção.",
            "items": [
                {
                    "purchase_order_item_id": order_item["id"],
                    "quantity": "1.0000",
                    "lot_id": lot_id,
                }
            ],
        },
        key="purchase-return-vertical-001",
    )
    assert purchase_return["return"]["status"] == "confirmed"

    responsible = _post(
        local_env,
        "/api/v1/people",
        {"full_name": "Responsável Patrimonial Vertical", "cpf": "72727272727"},
        key="asset-responsible-vertical-001",
    )
    borrower = _post(
        local_env,
        "/api/v1/people",
        {"full_name": "Tomador Patrimonial Vertical", "cpf": "83838383838"},
        key="asset-borrower-vertical-001",
    )
    location = _post(
        local_env,
        "/api/v1/asset-locations",
        {"code": "LAB-01", "name": "Laboratório 01"},
        key="asset-location-vertical-001",
    )
    destination = _post(
        local_env,
        "/api/v1/asset-locations",
        {"code": "LAB-02", "name": "Laboratório 02"},
        key="asset-location-vertical-002",
    )
    asset = _post(
        local_env,
        "/api/v1/assets",
        {
            "tag": "PAT-EQ-2026-001",
            "name": "Equipamento Educacional 01",
            "location_id": location["id"],
            "product_id": product["id"],
            "receipt_item_id": receipt_item_id,
            "description": "Equipamento incorporado a partir do recebimento.",
            "serial_number": "SERIAL-EDU-0001",
            "responsible_person_id": responsible["id"],
            "acquisition_date": "2026-01-15",
            "acquisition_cost": "1200.00",
            "useful_life_months": 60,
            "residual_value": "0.00",
            "warranty_until": "2027-01-15",
            "metadata": {"source": "procurement"},
        },
        key="asset-create-vertical-001",
    )
    asset_id = asset["asset"]["id"]
    assert asset["asset"]["status"] == "active"
    assert asset["asset"]["receipt_item_id"] == receipt_item_id

    transferred = _post(
        local_env,
        f"/api/v1/assets/{asset_id}/transfers",
        {
            "location_id": destination["id"],
            "responsible_person_id": responsible["id"],
            "reason": "Transferência para laboratório de robótica.",
        },
        expected=200,
    )
    assert transferred["asset"]["location_id"] == destination["id"]

    loan = _post(
        local_env,
        f"/api/v1/assets/{asset_id}/loans",
        {
            "borrower_person_id": borrower["id"],
            "expected_return_at": "2026-08-20T18:00:00Z",
            "condition_out": "Equipamento em perfeito estado.",
        },
        key="asset-loan-vertical-001",
    )
    assert loan["asset"]["status"] == "loaned"

    maintenance_during_loan = local_env.client.post(
        f"/api/v1/assets/{asset_id}/maintenances",
        headers=local_env.alpha_headers(**{"Idempotency-Key": "maintenance-during-loan-001"}),
        json={
            "maintenance_type": "preventive",
            "scheduled_on": "2026-08-25",
            "estimated_cost": "100.00",
            "description": "Manutenção que deve ser bloqueada durante empréstimo.",
        },
    )
    assert maintenance_during_loan.status_code == 409, maintenance_during_loan.text
    assert maintenance_during_loan.json()["code"] == "ASSET_MAINTENANCE_NOT_ALLOWED"

    returned_loan = _post(
        local_env,
        f"/api/v1/asset-loans/{loan['loan']['id']}/return",
        {"condition_in": "Equipamento devolvido sem avarias."},
        expected=200,
    )
    assert returned_loan["asset"]["status"] == "active"

    maintenance = _post(
        local_env,
        f"/api/v1/assets/{asset_id}/maintenances",
        {
            "maintenance_type": "preventive",
            "scheduled_on": "2026-08-25",
            "supplier_id": supplier["id"],
            "estimated_cost": "100.00",
            "description": "Revisão preventiva do equipamento.",
        },
        key="asset-maintenance-vertical-001",
    )
    started = _post(
        local_env,
        f"/api/v1/asset-maintenances/{maintenance['id']}/start",
        {},
        expected=200,
    )
    assert started["asset"]["status"] == "maintenance"
    completed = _post(
        local_env,
        f"/api/v1/asset-maintenances/{maintenance['id']}/complete",
        {"result_notes": "Revisão concluída com sucesso.", "actual_cost": "95.00"},
        expected=200,
    )
    assert completed["asset"]["status"] == "active"

    depreciation_payload = {"competence": "2026-02"}
    depreciation = _post(
        local_env,
        f"/api/v1/assets/{asset_id}/depreciations",
        depreciation_payload,
        key="asset-depreciation-vertical-001",
    )
    depreciation_replay = _post(
        local_env,
        f"/api/v1/assets/{asset_id}/depreciations",
        depreciation_payload,
        key="asset-depreciation-vertical-001",
    )
    assert depreciation_replay["depreciation"]["id"] == depreciation["depreciation"]["id"]
    assert float(depreciation["depreciation"]["depreciation_amount"]) == 20.0

    detail = local_env.client.get(f"/api/v1/assets/{asset_id}", headers=local_env.alpha_headers())
    assert detail.status_code == 200, detail.text
    detail_json = detail.json()
    assert detail_json["asset"]["status"] == "active"
    assert len(detail_json["movements"]) >= 4
    assert len(detail_json["maintenances"]) == 1
    assert len(detail_json["loans"]) == 1
    assert len(detail_json["depreciations"]) == 1

    cross_tenant_asset = local_env.client.get(
        f"/api/v1/assets/{asset_id}", headers=local_env.beta_headers()
    )
    assert cross_tenant_asset.status_code == 404, cross_tenant_asset.text
    assert cross_tenant_asset.json()["code"] == "ASSET_NOT_FOUND"

    tenant_id = local_env.alpha_tenant["id"]
    store = local_env.client.app.state.data_router.tenant_store(tenant_id)
    balance = store.fetch_one(
        "SELECT quantity,reserved FROM stock_balances WHERE tenant_id=? AND product_id=? AND warehouse='default'",
        (tenant_id, product["id"]),
    )
    lot = store.fetch_one(
        "SELECT quantity,reserved_quantity FROM inventory_lots WHERE tenant_id=? AND id=?",
        (tenant_id, lot_id),
    )
    assert float(balance["quantity"]) == 3.0
    assert float(balance["reserved"]) == 0.0
    assert float(lot["quantity"]) == 3.0
    assert float(lot["reserved_quantity"]) == 0.0
