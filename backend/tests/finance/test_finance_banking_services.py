from __future__ import annotations


def _post(env, path: str, payload: dict, *, expected: int = 201):
    response = env.client.post(path, headers=env.alpha_headers(), json=payload)
    assert response.status_code == expected, response.text
    return response.json()


def test_service_order_uses_server_price_generates_installments_and_can_be_listed(local_env):
    service = _post(
        local_env,
        "/api/v1/services",
        {
            "code": "CURSO-ROB",
            "name": "Robótica",
            "price": "150.00",
            "recurrence": "monthly",
            "nbs": "123456789",
            "lc116_code": "08.02",
        },
    )

    order = _post(
        local_env,
        "/api/v1/service-orders",
        {
            "items": [{"service_id": service["id"], "quantity": "2"}],
            "installment_count": 2,
            "first_due_date": "2026-08-10",
            "competence": "2026-08",
        },
    )
    assert order["total_amount"] == "300.00"
    assert order["installments"] == 2

    listed = local_env.client.get(
        "/api/v1/service-orders",
        headers=local_env.alpha_headers(),
    )
    assert listed.status_code == 200, listed.text
    saved = next(item for item in listed.json()["items"] if item["id"] == order["id"])
    assert saved["total_amount"] in ("300.00", 300, 300.0)
    assert len(saved["items"]) == 1
    assert saved["items"][0]["unit_price"] in ("150.00", 150, 150.0)

    installments = local_env.client.get(
        "/api/v1/finance/installments",
        headers=local_env.alpha_headers(),
    )
    assert installments.status_code == 200, installments.text
    generated = [
        row
        for row in installments.json()["items"]
        if row["financial_contract_id"] == order["financial_contract_id"]
    ]
    assert [str(row["original_amount"]) for row in generated] in (["150", "150"], ["150.0", "150.0"], ["150.00", "150.00"])


def test_bank_import_is_sha256_idempotent(local_env):
    account = _post(
        local_env,
        "/api/v1/banking/accounts",
        {
            "name": "Conta Conciliação",
            "bank_code": "001",
            "pix_key": "financeiro@example.test",
        },
    )
    payload = {
        "source_type": "csv",
        "source_content": "data;descricao;valor\n2026-08-08;PIX;250.00\n",
        "transactions": [
            {
                "external_id": "BANK-001",
                "posted_at": "2026-08-08T12:00:00+00:00",
                "description": "PIX recebido",
                "amount": "250.00",
                "direction": "credit",
            }
        ],
    }
    first = _post(
        local_env,
        f"/api/v1/banking/accounts/{account['id']}/imports",
        payload,
    )
    assert first["idempotent"] is False
    assert first["transactions"] == 1
    assert len(first["source_sha256"]) == 64

    second = _post(
        local_env,
        f"/api/v1/banking/accounts/{account['id']}/imports",
        payload,
    )
    assert second["id"] == first["id"]
    assert second["idempotent"] is True
    assert second["transactions"] == 0


def test_refund_bank_reconciliation_and_financial_renegotiation(local_env):
    contract = _post(
        local_env,
        "/api/v1/finance/contracts",
        {
            "description": "Contrato financeiro para renegociação",
            "total_amount": "1000.00",
            "competence_rule": "billing",
        },
    )
    plan = _post(
        local_env,
        f"/api/v1/finance/contracts/{contract['id']}/installments",
        {"count": 2, "first_due_date": "2026-08-10", "interval_months": 1},
    )
    first, second = plan["installments"]

    payment_response = local_env.client.post(
        "/api/v1/finance/payments",
        headers=local_env.alpha_headers(**{"Idempotency-Key": "finance-payment-001"}),
        json={
            "method": "bank_transfer",
            "amount": "500.00",
            "external_reference": "PAY-500",
            "allocations": [{"installment_id": first["id"], "amount": "500.00"}],
        },
    )
    assert payment_response.status_code == 201, payment_response.text
    payment = payment_response.json()

    refund_payload = {
        "amount": "200.00",
        "method": "bank_transfer",
        "reason": "Estorno parcial solicitado pelo responsável",
        "external_reference": "REF-200",
        "allocations": [{"installment_id": first["id"], "amount": "200.00"}],
    }
    refund_headers = local_env.alpha_headers(**{"Idempotency-Key": "finance-refund-001"})
    refund_response = local_env.client.post(
        f"/api/v1/finance/payments/{payment['id']}/refunds",
        headers=refund_headers,
        json=refund_payload,
    )
    assert refund_response.status_code == 201, refund_response.text
    refund = refund_response.json()
    assert refund["payment_state"] == "partially_refunded"
    assert refund["allocations"][0]["state"] == "partial"

    replay = local_env.client.post(
        f"/api/v1/finance/payments/{payment['id']}/refunds",
        headers=refund_headers,
        json=refund_payload,
    )
    assert replay.status_code == 201, replay.text
    assert replay.json()["id"] == refund["id"]

    installments = local_env.client.get(
        "/api/v1/finance/installments",
        headers=local_env.alpha_headers(),
    ).json()["items"]
    first_saved = next(row for row in installments if row["id"] == first["id"])
    assert float(first_saved["paid_amount"]) == 300.0
    assert first_saved["state"] == "partial"

    account = _post(
        local_env,
        "/api/v1/banking/accounts",
        {"name": "Conta Conciliação Financeira", "pix_key": "financeiro@escola.test"},
    )
    imported = _post(
        local_env,
        f"/api/v1/banking/accounts/{account['id']}/imports",
        {
            "source_type": "csv",
            "source_content": "id;valor\nTX-500;500.00\nTX-400;400.00\n",
            "transactions": [
                {
                    "external_id": "TX-500",
                    "posted_at": "2026-08-08T12:00:00+00:00",
                    "description": "Transferência identificada",
                    "amount": "500.00",
                    "direction": "credit",
                },
                {
                    "external_id": "TX-400",
                    "posted_at": "2026-08-08T12:01:00+00:00",
                    "description": "Valor divergente",
                    "amount": "400.00",
                    "direction": "credit",
                },
            ],
        },
    )
    assert imported["transactions"] == 2
    transactions = local_env.client.get(
        f"/api/v1/banking/transactions?account_id={account['id']}&state=unmatched",
        headers=local_env.alpha_headers(),
    )
    assert transactions.status_code == 200, transactions.text
    by_external = {row["external_id"]: row for row in transactions.json()["items"]}

    mismatch = local_env.client.post(
        f"/api/v1/banking/transactions/{by_external['TX-400']['id']}/reconcile",
        headers=local_env.alpha_headers(),
        json={"payment_id": payment["id"], "reason": "Tentativa de conciliação"},
    )
    assert mismatch.status_code == 409, mismatch.text
    assert mismatch.json()["code"] == "BANK_RECONCILIATION_AMOUNT_MISMATCH"

    reconciled = local_env.client.post(
        f"/api/v1/banking/transactions/{by_external['TX-500']['id']}/reconcile",
        headers=local_env.alpha_headers(),
        json={"payment_id": payment["id"], "reason": "Conciliação manual conferida"},
    )
    assert reconciled.status_code == 200, reconciled.text
    assert reconciled.json()["state"] == "matched"
    replay_reconciliation = local_env.client.post(
        f"/api/v1/banking/transactions/{by_external['TX-500']['id']}/reconcile",
        headers=local_env.alpha_headers(),
        json={"payment_id": payment["id"], "reason": "Replay"},
    )
    assert replay_reconciliation.status_code == 200, replay_reconciliation.text
    assert replay_reconciliation.json()["idempotent"] is True

    renegotiated_response = local_env.client.post(
        f"/api/v1/finance/contracts/{contract['id']}/renegotiate",
        headers=local_env.alpha_headers(),
        json={
            "installments": 3,
            "first_due_date": "2026-10-10",
            "interval_months": 1,
            "new_total_amount": "650.00",
            "reason": "Acordo financeiro homologado",
            "terms": {"discount_reason": "acordo"},
        },
    )
    assert renegotiated_response.status_code == 201, renegotiated_response.text
    renegotiation = renegotiated_response.json()
    assert float(renegotiation["original_open_amount"]) == 700.0
    assert float(renegotiation["new_total_amount"]) == 650.0
    assert len(renegotiation["installments"]) == 3
    assert round(sum(float(item["amount"]) for item in renegotiation["installments"]), 2) == 650.0

    original_installments = local_env.client.get(
        "/api/v1/finance/installments",
        headers=local_env.alpha_headers(),
    ).json()["items"]
    original_states = {
        row["id"]: row["state"]
        for row in original_installments
        if row["id"] in {first["id"], second["id"]}
    }
    assert original_states == {first["id"]: "renegotiated", second["id"]: "renegotiated"}

    ledger = local_env.client.get(
        "/api/v1/finance/ledger",
        headers=local_env.alpha_headers(),
    )
    assert ledger.status_code == 200, ledger.text
    entry_types = [row["entry_type"] for row in ledger.json()["items"]]
    assert "receipt" in entry_types
    assert "refund" in entry_types
