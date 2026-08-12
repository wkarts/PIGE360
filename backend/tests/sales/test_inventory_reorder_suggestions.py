from __future__ import annotations


def _post(env, path: str, payload: dict, *, key: str | None = None, expected: int = 201, beta: bool = False):
    headers_factory = env.beta_headers if beta else env.alpha_headers
    headers = headers_factory(**({"Idempotency-Key": key} if key else {}))
    response = env.client.post(path, headers=headers, json=payload)
    assert response.status_code == expected, response.text
    return response.json()


def _create_product(env, sku: str, name: str, *, product_type: str = "product", cost: str = "10.00"):
    return _post(
        env,
        "/api/v1/products",
        {
            "sku": sku,
            "name": name,
            "product_type": product_type,
            "cost": cost,
            "sale_price": "20.00",
        },
    )


def _adjust(env, product_id: str, amount: str):
    return _post(
        env,
        f"/api/v1/products/{product_id}/stock-adjustments",
        {"quantity": amount, "warehouse": "default", "reason": "Carga de teste do estoque mínimo"},
        key=f"stock-adjustment-{product_id}-{amount}",
        expected=200,
    )


def test_minimum_stock_generates_idempotent_canteen_suggestion_and_converts_to_requisition(local_env):
    food = _create_product(
        local_env,
        "CANT-REP-001",
        "Lanche escolar para reposição",
        product_type="food",
        cost="8.50",
    )
    _adjust(local_env, food["id"], "2")
    supplier = _post(
        local_env,
        "/api/v1/suppliers",
        {"legal_name": "Fornecedor da Cantina Ltda", "code": "FOR-CANT-REP"},
        key="supplier-canteen-reorder-001",
    )

    payload = {
        "product_id": food["id"],
        "warehouse_id": "default",
        "minimum_quantity": "5.0000",
        "target_quantity": "12.0000",
        "lead_time_days": 3,
        "preferred_supplier_id": supplier["id"],
    }
    policy = _post(
        local_env,
        "/api/v1/inventory/reorder-policies",
        payload,
        key="reorder-policy-canteen-001",
    )
    replay = _post(
        local_env,
        "/api/v1/inventory/reorder-policies",
        payload,
        key="reorder-policy-canteen-001",
    )
    assert replay["id"] == policy["id"]
    assert policy["product_type"] == "food"
    assert float(policy["stock"]["available_quantity"]) == 2.0

    invalid = local_env.client.post(
        "/api/v1/inventory/reorder-policies",
        headers=local_env.alpha_headers(**{"Idempotency-Key": "reorder-policy-invalid-001"}),
        json={**payload, "minimum_quantity": "10", "target_quantity": "5"},
    )
    assert invalid.status_code == 422, invalid.text

    generated = _post(
        local_env,
        "/api/v1/inventory/purchase-suggestions/generate",
        {"product_ids": [food["id"]]},
        key="generate-canteen-suggestion-001",
        expected=200,
    )
    assert generated["summary"] == {
        "policies_evaluated": 1,
        "created": 1,
        "refreshed": 0,
        "superseded": 0,
        "not_required": 0,
    }
    suggestion = generated["items"][0]
    assert suggestion["product_type"] == "food"
    assert suggestion["status"] == "open"
    assert float(suggestion["suggested_quantity"]) == 10.0
    assert float(suggestion["estimated_unit_cost"]) == 8.5
    assert float(suggestion["estimated_total"]) == 85.0

    generation_replay = _post(
        local_env,
        "/api/v1/inventory/purchase-suggestions/generate",
        {"product_ids": [food["id"]]},
        key="generate-canteen-suggestion-001",
        expected=200,
    )
    assert generation_replay["items"][0]["id"] == suggestion["id"]

    beta_list = local_env.client.get(
        "/api/v1/inventory/reorder-policies",
        headers=local_env.beta_headers(),
    )
    assert beta_list.status_code == 200, beta_list.text
    assert beta_list.json()["items"] == []
    beta_detail = local_env.client.get(
        f"/api/v1/inventory/reorder-policies/{policy['id']}",
        headers=local_env.beta_headers(),
    )
    assert beta_detail.status_code == 404, beta_detail.text

    converted = _post(
        local_env,
        f"/api/v1/inventory/purchase-suggestions/{suggestion['id']}/convert",
        {
            "expected_version": suggestion["version"],
            "justification": "Reposição automática validada pela gestão da cantina.",
        },
        key="convert-canteen-suggestion-001",
    )
    assert converted["suggestion"]["status"] == "converted"
    assert converted["requisition"]["status"] == "draft"
    assert converted["suggestion"]["requisition_id"] == converted["requisition"]["id"]
    assert float(converted["items"][0]["quantity"]) == 10.0

    conversion_replay = _post(
        local_env,
        f"/api/v1/inventory/purchase-suggestions/{suggestion['id']}/convert",
        {
            "expected_version": suggestion["version"],
            "justification": "Reposição automática validada pela gestão da cantina.",
        },
        key="convert-canteen-suggestion-001",
    )
    assert conversion_replay["requisition"]["id"] == converted["requisition"]["id"]

    tenant_id = local_env.alpha_tenant["id"]
    store = local_env.client.app.state.data_router.tenant_store(tenant_id)
    event_types = [
        row["event_type"]
        for row in store.fetch_all(
            "SELECT event_type FROM outbox_events WHERE tenant_id=? AND aggregate_id IN (?,?) ORDER BY created_at,id",
            (tenant_id, suggestion["id"], converted["requisition"]["id"]),
        )
    ]
    assert "PurchaseSuggestionGenerated" in event_types
    assert "PurchaseSuggestionConverted" in event_types
    assert "PurchaseRequisitionCreated" in event_types
    audit_actions = [
        row["action"]
        for row in store.fetch_all(
            "SELECT action FROM audit_log WHERE tenant_id=? AND aggregate_id IN (?,?) ORDER BY created_at,id",
            (tenant_id, suggestion["id"], converted["requisition"]["id"]),
        )
    ]
    assert "generate" in audit_actions
    assert "convert" in audit_actions
    assert "create_from_suggestion" in audit_actions


def test_inbound_orders_refresh_supersede_dismiss_and_policy_concurrency(local_env):
    product = _create_product(local_env, "REP-INBOUND-001", "Material com compra em trânsito", cost="15.00")
    _adjust(local_env, product["id"], "1")
    supplier = _post(
        local_env,
        "/api/v1/suppliers",
        {"legal_name": "Fornecedor de Material Ltda", "code": "FOR-REP-INBOUND"},
        key="supplier-reorder-inbound-001",
    )
    policy = _post(
        local_env,
        "/api/v1/inventory/reorder-policies",
        {
            "product_id": product["id"],
            "warehouse_id": "default",
            "minimum_quantity": "5",
            "target_quantity": "10",
            "preferred_supplier_id": supplier["id"],
        },
        key="reorder-policy-inbound-001",
    )
    order = _post(
        local_env,
        "/api/v1/procurement/orders",
        {
            "supplier_id": supplier["id"],
            "warehouse_id": "default",
            "items": [{"product_id": product["id"], "quantity": "4", "unit_price": "15.00"}],
        },
        key="reorder-draft-order-001",
    )
    first = _post(
        local_env,
        "/api/v1/inventory/purchase-suggestions/generate",
        {"product_ids": [product["id"]]},
        key="generate-before-order-approval-001",
        expected=200,
    )["items"][0]
    assert float(first["open_purchase_quantity"]) == 0.0
    assert float(first["suggested_quantity"]) == 9.0

    approved = _post(
        local_env,
        f"/api/v1/procurement/orders/{order['order']['id']}/approve",
        {"reason": "Pedido necessário para recomposição do estoque."},
        expected=200,
    )
    assert approved["status"] == "approved"
    regenerated = _post(
        local_env,
        "/api/v1/inventory/purchase-suggestions/generate",
        {"product_ids": [product["id"]]},
        key="generate-after-order-approval-001",
        expected=200,
    )
    assert regenerated["summary"]["superseded"] == 1
    assert regenerated["summary"]["not_required"] == 1
    assert regenerated["items"] == []
    superseded = local_env.client.get(
        f"/api/v1/inventory/purchase-suggestions/{first['id']}",
        headers=local_env.alpha_headers(),
    )
    assert superseded.status_code == 200, superseded.text
    assert superseded.json()["status"] == "superseded"
    assert float(superseded.json()["open_purchase_quantity"]) == 4.0

    second_product = _create_product(local_env, "REP-DISMISS-001", "Material para descarte de sugestão")
    second_policy = _post(
        local_env,
        "/api/v1/inventory/reorder-policies",
        {
            "product_id": second_product["id"],
            "warehouse_id": "default",
            "minimum_quantity": "2",
            "target_quantity": "6",
        },
        key="reorder-policy-dismiss-001",
    )
    second_suggestion = _post(
        local_env,
        "/api/v1/inventory/purchase-suggestions/generate",
        {"product_ids": [second_product["id"]]},
        key="generate-dismissable-suggestion-001",
        expected=200,
    )["items"][0]
    dismissed = _post(
        local_env,
        f"/api/v1/inventory/purchase-suggestions/{second_suggestion['id']}/dismiss",
        {"expected_version": second_suggestion["version"], "reason": "Compra adiada após revisão orçamentária."},
        key="dismiss-suggestion-001",
        expected=200,
    )
    assert dismissed["status"] == "dismissed"
    assert dismissed["closure_reason"] == "Compra adiada após revisão orçamentária."

    replacement = _post(
        local_env,
        "/api/v1/inventory/purchase-suggestions/generate",
        {"product_ids": [second_product["id"]]},
        key="generate-replacement-suggestion-001",
        expected=200,
    )["items"][0]
    assert replacement["id"] != second_suggestion["id"]

    updated_policy = local_env.client.patch(
        f"/api/v1/inventory/reorder-policies/{second_policy['id']}",
        headers=local_env.alpha_headers(),
        json={
            "minimum_quantity": "3",
            "target_quantity": "7",
            "expected_version": second_policy["version"],
        },
    )
    assert updated_policy.status_code == 200, updated_policy.text
    updated_policy_data = updated_policy.json()
    assert updated_policy_data["version"] == 2

    stale = local_env.client.patch(
        f"/api/v1/inventory/reorder-policies/{second_policy['id']}",
        headers=local_env.alpha_headers(),
        json={"state": "inactive", "expected_version": 1},
    )
    assert stale.status_code == 409, stale.text
    assert stale.json()["code"] == "OPTIMISTIC_CONCURRENCY_CONFLICT"

    inactivated = local_env.client.patch(
        f"/api/v1/inventory/reorder-policies/{second_policy['id']}",
        headers=local_env.alpha_headers(),
        json={"state": "inactive", "expected_version": updated_policy_data["version"]},
    )
    assert inactivated.status_code == 200, inactivated.text
    assert inactivated.json()["status"] == "inactive"
    superseded_by_policy = local_env.client.get(
        f"/api/v1/inventory/purchase-suggestions/{replacement['id']}",
        headers=local_env.alpha_headers(),
    )
    assert superseded_by_policy.status_code == 200, superseded_by_policy.text
    assert superseded_by_policy.json()["status"] == "superseded"
    assert superseded_by_policy.json()["closure_reason"] == "policy_inactivated"

    beta_cross_create = local_env.client.post(
        "/api/v1/inventory/reorder-policies",
        headers=local_env.beta_headers(**{"Idempotency-Key": "cross-tenant-reorder-policy-001"}),
        json={
            "product_id": second_product["id"],
            "warehouse_id": "default",
            "minimum_quantity": "1",
            "target_quantity": "2",
        },
    )
    assert beta_cross_create.status_code == 404, beta_cross_create.text
