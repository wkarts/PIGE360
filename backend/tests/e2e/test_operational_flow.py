from __future__ import annotations


def post_ok(env, path, payload, *, key=None, expected=201):
    headers = env.alpha_headers(**({"Idempotency-Key": key} if key else {}))
    response = env.client.post(path, headers=headers, json=payload)
    assert response.status_code == expected, f"{path}: {response.status_code} {response.text}"
    return response.json()


def test_end_to_end_relational_school_finance_sales_fiscal_hr_and_documents(local_env):
    institution = post_ok(local_env, "/api/v1/institutions", {"legal_name":"Escola Alpha Ltda","trade_name":"Escola Alpha","cnpj":"12345678000190","education_system":"private"})
    unit = post_ok(local_env, "/api/v1/units", {"institution_id":institution["id"],"code":"MATRIZ","name":"Unidade Matriz","timezone":"America/Bahia","address":{}})
    year = post_ok(local_env, "/api/v1/academic-years", {"institution_id":institution["id"],"name":"2026","starts_on":"2026-01-20","ends_on":"2026-12-18"})
    program = post_ok(local_env, "/api/v1/programs", {"institution_id":institution["id"],"code":"EF2","name":"Ensino Fundamental II","education_level":"fundamental","modality":"presencial"})
    curriculum = post_ok(local_env, "/api/v1/curricula", {"program_id":program["id"],"code":"CURR-2026","name":"Currículo 2026","effective_from":"2026-01-01"})
    component = post_ok(local_env, "/api/v1/curriculum-components", {"curriculum_id":curriculum["id"],"code":"MAT","name":"Matemática","workload_hours":160})
    group = post_ok(local_env, "/api/v1/class-groups", {"unit_id":unit["id"],"academic_year_id":year["id"],"program_id":program["id"],"curriculum_id":curriculum["id"],"code":"7A","name":"7º A","shift":"morning","capacity":30})

    person = post_ok(local_env, "/api/v1/people", {"full_name":"Maria Estudante","cpf":"12345678909","email":"maria@example.com"}, key="e2e-person-student")
    student = post_ok(local_env, "/api/v1/students", {"person_id":person["id"],"registration_number":"2026-0001"})
    enrollment = post_ok(local_env, "/api/v1/enrollments", {"student_id":student["id"],"institution_id":institution["id"],"unit_id":unit["id"],"program_id":program["id"],"curriculum_id":curriculum["id"],"academic_year_id":year["id"],"class_group_id":group["id"],"enrollment_number":"MAT-2026-0001"}, key="e2e-enrollment")
    activated = post_ok(local_env, f"/api/v1/enrollments/{enrollment['id']}/activate", {"expected_version":1,"reason":"Documentação conferida"}, expected=200)
    assert activated["state"] == "active"

    financial = post_ok(local_env, "/api/v1/finance/contracts", {"enrollment_id":enrollment["id"],"description":"Anuidade escolar 2026","total_amount":"12000.00","competence_rule":"billing"})
    installments = post_ok(local_env, f"/api/v1/finance/contracts/{financial['id']}/installments", {"count":12,"first_due_date":"2026-01-10","interval_months":1}, expected=201)
    assert len(installments["installments"]) == 12
    first_installment = installments["installments"][0]
    account = post_ok(local_env, "/api/v1/banking/accounts", {"name":"Conta Escola Alpha","bank_code":"001","branch":"1234","account_number":"56789-0","pix_key":"financeiro@escolaalpha.test","pix_receiver_name":"ESCOLA ALPHA","pix_receiver_city":"SALVADOR"})
    pix = post_ok(local_env, f"/api/v1/banking/accounts/{account['id']}/pix-charges", {"installment_id":first_installment["id"]})
    assert pix["br_code"].startswith("000201")
    paid = post_ok(local_env, f"/api/v1/banking/pix-charges/{pix['id']}/confirm", {"end_to_end_id":"E123456789012345678901234567890"}, expected=200)
    assert paid["state"] == "paid"

    product = post_ok(local_env, "/api/v1/products", {"sku":"LIVRO-MAT-7","barcode":"7890000000001","name":"Livro Matemática 7º Ano","product_type":"book","ncm":"49019900","unit":"UN","cost":"45.00","sale_price":"80.00"})
    adjusted = post_ok(local_env, f"/api/v1/products/{product['id']}/stock-adjustments", {"quantity":"10","warehouse":"default","reason":"Estoque inicial","unit_cost":"45.00"}, key="e2e-stock", expected=200)
    assert float(adjusted["quantity"]) == 10.0
    cash = post_ok(local_env, "/api/v1/pos/cash-sessions/open", {"terminal_code":"PDV-01","opening_amount":"100.00"})
    sale = post_ok(local_env, "/api/v1/sales", {"cash_session_id":cash["id"],"channel":"pos","student_id":student["id"],"items":[{"product_id":product["id"],"quantity":"1","discount":"0"}],"payments":[{"method":"pix","amount":"80.00","external_reference":"POS-PIX-1"}],"discount":"0","request_fiscal_document":True}, key="e2e-sale")
    assert sale["state"] == "completed" and sale["fiscal_document_id"]
    products = local_env.client.get("/api/v1/products", headers=local_env.alpha_headers()).json()["items"]
    assert next(x for x in products if x["id"] == product["id"])["stock_quantity"] in (9, 9.0, "9", "9.0")

    fiscal_profile = post_ok(local_env, "/api/v1/fiscal/profiles", {"establishment_name":"Escola Alpha","cnpj":"12345678000190","tax_regime":"simples_nacional","uf":"BA","municipality_code":"2927408","environment":"homologation"})
    post_ok(local_env, "/api/v1/fiscal/rules", {"fiscal_profile_id":fiscal_profile["id"],"operation_type":"retail_sale","item_kind":"product","classification_key":"49019900","effective_from":"2026-01-01","rules":{"rates":{"IBS":"0.10","CBS":"0.90"},"mode":"simulation_only"}})
    simulation = post_ok(local_env, "/api/v1/fiscal/simulate", {"fiscal_profile_id":fiscal_profile["id"],"operation_type":"retail_sale","item_kind":"product","classification_key":"49019900","total_amount":"80.00","context":{"regime":"simples_nacional"}}, expected=200)
    assert simulation["classified"] is True and simulation["rule_version"] == 1

    employee_person = post_ok(local_env, "/api/v1/people", {"full_name":"João Professor","cpf":"98765432100","email":"joao@example.com"}, key="e2e-person-employee")
    employee = post_ok(local_env, "/api/v1/employees", {"person_id":employee_person["id"],"employee_number":"EMP-001","department":"Pedagógico","position":"Professor","admission_date":"2026-01-05"})
    post_ok(local_env, "/api/v1/hr/employment-contracts", {"employee_id":employee["id"],"contract_type":"CLT","starts_on":"2026-01-05","salary":"5000.00","weekly_hours":"40","schedule":{"monday":"08:00-17:00"}})
    post_ok(local_env, "/api/v1/payroll/rules", {"code":"BONUS","name":"Gratificação","direction":"earning","calculation_type":"fixed","basis":"salary","value":"500.00","effective_from":"2026-01-01","priority":10})
    payroll = post_ok(local_env, "/api/v1/payroll/runs", {"competence":"2026-08","run_type":"monthly"})
    assert payroll["employees"] == 1 and payroll["net_total"] == "5500.00"

    document = local_env.client.post(
        "/api/v1/documents?owner_type=student&category=academic&owner_id=" + student["id"],
        headers=local_env.alpha_headers(),
        files={"file": ("declaracao.pdf", b"%PDF-1.4\nPIGE360 TEST DOCUMENT\n%%EOF", "application/pdf")},
    )
    assert document.status_code == 201, document.text
    assert len(document.json()["sha256"]) == 64
    download = local_env.client.get(f"/api/v1/documents/{document.json()['id']}/download", headers=local_env.alpha_headers())
    assert download.status_code == 200 and download.content.startswith(b"%PDF")

    beta_students = local_env.client.get("/api/v1/students", headers=local_env.beta_headers())
    assert beta_students.status_code == 200 and beta_students.json()["items"] == []
