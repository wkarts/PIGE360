from __future__ import annotations

from app.shared.domain.ids import iso_now, uuid7

CATALOGS = {
    "NCM": ("NCM", "digits", "12345678"),
    "NBS": ("NBS", "digits", "123456789"),
    "LC116": ("LC 116", "upper_alnum", "101"),
    "CFOP": ("CFOP", "digits", "5102"),
    "CEST": ("CEST", "digits", "1234567"),
    "CST": ("CST", "digits", "00"),
    "CSOSN": ("CSOSN", "digits", "102"),
    "CST_IBS_CBS": ("CST IBS/CBS", "digits", "000"),
    "CCLASSTRIB": ("cClassTrib", "upper_alnum", "000001"),
    "CBENEF": ("cBenef", "upper_alnum", "BA000001"),
}


def create_context(local_env):
    response = local_env.client.post(
        "/api/v1/fiscal/contexts",
        headers=local_env.alpha_headers(**{"Idempotency-Key": "catalog-context-001"}),
        json={"code":"MATRIZ-BA","establishment_name":"Matriz BA","cnpj":"12.345.678/0001-95"},
    )
    assert response.status_code == 201, response.text
    context=response.json()
    version=local_env.client.post(
        f"/api/v1/fiscal/contexts/{context['id']}/versions",
        headers=local_env.alpha_headers(**{"Idempotency-Key":"catalog-context-version-001"}),
        json={
            "tax_regime":"simples_nacional","uf":"BA","municipality_code":"2927408","valid_from":"2026-01-01",
            "environment":"homologation","rtc_mode":"optional_emit","ruleset_version":"RTC-2026",
            "scopes":[{"operation_type":"sale","item_kind":"product","recipient_scope":"company","document_type":"NF-e"}],
            "expected_context_version":1,
        },
    )
    assert version.status_code == 201, version.text
    published=local_env.client.post(
        f"/api/v1/fiscal/contexts/{context['id']}/versions/{version.json()['id']}/publish",
        headers=local_env.alpha_headers(**{"Idempotency-Key":"catalog-context-publish-001"}),
        json={"expected_context_version":2,"expected_version":1,"reason":"Publicação para classificação fiscal."},
    )
    assert published.status_code == 200, published.text
    return context


def create_catalogs(local_env):
    result={}
    for kind,(name,normalization,code) in CATALOGS.items():
        created=local_env.client.post(
            "/api/v1/fiscal/catalogs",
            headers=local_env.alpha_headers(**{"Idempotency-Key":f"catalog-create-{kind.lower()}"}),
            json={"kind":kind,"name":name,"normalization":normalization},
        )
        assert created.status_code == 201, created.text
        replay=local_env.client.post(
            "/api/v1/fiscal/catalogs",
            headers=local_env.alpha_headers(**{"Idempotency-Key":f"catalog-create-{kind.lower()}"}),
            json={"kind":kind,"name":name,"normalization":normalization},
        )
        assert replay.status_code == 201 and replay.json()["id"] == created.json()["id"]
        catalog=created.json()
        version=local_env.client.post(
            f"/api/v1/fiscal/catalogs/{catalog['id']}/versions",
            headers=local_env.alpha_headers(**{"Idempotency-Key":f"catalog-version-{kind.lower()}"}),
            json={"version_label":"2026.1","valid_from":"2026-01-01","source_name":"fixture oficial controlada de teste","schema_version":"1","entries":[{"code":code,"description":f"Código {kind} de teste"}]},
        )
        assert version.status_code == 201, version.text
        assert len(version.json()["source_sha256"]) == 64
        published=local_env.client.post(
            f"/api/v1/fiscal/catalogs/{catalog['id']}/versions/{version.json()['id']}/publish",
            headers=local_env.alpha_headers(**{"Idempotency-Key":f"catalog-publish-{kind.lower()}"}),
            json={"expected_version":1,"reason":"Publicação controlada do catálogo fiscal."},
        )
        assert published.status_code == 200, published.text
        result[kind]={"catalog":catalog,"version":published.json(),"code":code}
    return result


def test_fiscal_catalogs_are_versioned_effective_idempotent_and_tenant_isolated(local_env):
    catalogs=create_catalogs(local_env)
    listing=local_env.client.get("/api/v1/fiscal/catalogs",headers=local_env.alpha_headers())
    assert listing.status_code == 200
    assert {item["kind"] for item in listing.json()["items"]} == set(CATALOGS)

    ncm=catalogs["NCM"]
    resolved=local_env.client.get(f"/api/v1/fiscal/catalogs/{ncm['catalog']['id']}/resolve/12.345.678?occurred_on=2026-08-10",headers=local_env.alpha_headers())
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["entry"]["code"] == "12345678"

    beta=local_env.client.get(f"/api/v1/fiscal/catalogs/{ncm['catalog']['id']}",headers=local_env.beta_headers())
    assert beta.status_code == 404

    store=local_env.client.app.state.data_router.tenant_store(local_env.alpha_tenant["id"])
    assert store.scalar("SELECT COUNT(*) FROM outbox_events WHERE tenant_id=? AND event_type='FiscalCatalogVersionPublished'",(local_env.alpha_tenant["id"],)) == 10
    assert store.scalar("SELECT COUNT(*) FROM audit_log WHERE tenant_id=? AND aggregate_type='fiscal_catalog'",(local_env.alpha_tenant["id"],)) >= 20


def test_classification_rules_validate_catalogs_and_calculate_readiness(local_env):
    context=create_context(local_env)
    catalogs=create_catalogs(local_env)
    store=local_env.client.app.state.data_router.tenant_store(local_env.alpha_tenant["id"])
    now=iso_now(); product_id=uuid7(); service_id=uuid7()
    with store.transaction() as conn:
        conn.execute("INSERT INTO products(id,tenant_id,sku,name,product_type,unit,cost,sale_price,fiscal_profile_json,allergen_json,restriction_json,state,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(product_id,local_env.alpha_tenant["id"],"PROD-FISCAL","Produto Fiscal","product","UN","10.00","20.00","{}","[]","{}","active",now,now))
        conn.execute("INSERT INTO services(id,tenant_id,code,name,price,fiscal_profile_json,state,service_type,recurrence_type,unit_of_measure,taxable,metadata_json,version,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(service_id,local_env.alpha_tenant["id"],"SERV-FISCAL","Serviço Fiscal","100.00","{}","active","administrative","one_time","unit",1,"{}",1,now,now))

    product_rule=local_env.client.post(
        "/api/v1/fiscal/classification-rules",
        headers=local_env.alpha_headers(**{"Idempotency-Key":"class-product-001"}),
        json={
            "fiscal_context_id":context["id"],"establishment_code":"MATRIZ-BA","item_kind":"product","item_id":product_id,
            "operation_type":"sale","valid_from":"2026-01-01","priority":200,
            "ncm":catalogs["NCM"]["code"],"cfop":catalogs["CFOP"]["code"],"cest":catalogs["CEST"]["code"],
            "csosn":catalogs["CSOSN"]["code"],"cst_ibs_cbs":catalogs["CST_IBS_CBS"]["code"],"cclasstrib":catalogs["CCLASSTRIB"]["code"],"cbenef":catalogs["CBENEF"]["code"],
        },
    )
    assert product_rule.status_code == 201, product_rule.text
    pub=local_env.client.post(
        f"/api/v1/fiscal/classification-rules/{product_rule.json()['id']}/publish",
        headers=local_env.alpha_headers(**{"Idempotency-Key":"class-product-publish-001"}),
        json={"expected_version":1,"reason":"Classificação de produto validada."},
    )
    assert pub.status_code == 200, pub.text

    service_rule=local_env.client.post(
        "/api/v1/fiscal/classification-rules",
        headers=local_env.alpha_headers(**{"Idempotency-Key":"class-service-001"}),
        json={
            "fiscal_context_id":context["id"],"establishment_code":"MATRIZ-BA","item_kind":"service","item_id":service_id,
            "operation_type":"sale","valid_from":"2026-01-01","priority":200,
            "nbs":catalogs["NBS"]["code"],"lc116":catalogs["LC116"]["code"],"municipal_code":"0101",
            "cst_ibs_cbs":catalogs["CST_IBS_CBS"]["code"],"cclasstrib":catalogs["CCLASSTRIB"]["code"],
        },
    )
    assert service_rule.status_code == 201, service_rule.text
    service_pub=local_env.client.post(
        f"/api/v1/fiscal/classification-rules/{service_rule.json()['id']}/publish",
        headers=local_env.alpha_headers(**{"Idempotency-Key":"class-service-publish-001"}),
        json={"expected_version":1,"reason":"Classificação de serviço validada."},
    )
    assert service_pub.status_code == 200, service_pub.text

    readiness=local_env.client.get(f"/api/v1/fiscal/readiness?fiscal_context_id={context['id']}&establishment_code=MATRIZ-BA&occurred_on=2026-08-10&operation_type=sale",headers=local_env.alpha_headers())
    assert readiness.status_code == 200, readiness.text
    body=readiness.json()
    assert body["total_items"] == 2 and body["ready_items"] == 2 and body["pending_items"] == 0
    assert body["readiness_percentage"] == 100.0

    invalid=local_env.client.post(
        "/api/v1/fiscal/classification-rules",
        headers=local_env.alpha_headers(**{"Idempotency-Key":"class-invalid-code-001"}),
        json={"fiscal_context_id":context["id"],"item_kind":"product","operation_type":"sale","valid_from":"2026-01-01","ncm":"99999999"},
    )
    assert invalid.status_code == 422, invalid.text
    assert invalid.json()["code"] == "FISCAL_CLASSIFICATION_CODE_NOT_EFFECTIVE"

    beta=local_env.client.get(f"/api/v1/fiscal/readiness?fiscal_context_id={context['id']}",headers=local_env.beta_headers())
    assert beta.status_code == 404
    assert store.scalar("SELECT COUNT(*) FROM outbox_events WHERE tenant_id=? AND event_type='FiscalClassificationRulePublished'",(local_env.alpha_tenant["id"],)) == 2
