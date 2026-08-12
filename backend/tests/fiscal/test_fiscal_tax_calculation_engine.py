from __future__ import annotations

from decimal import Decimal


def _create_context(local_env, *, rtc_mode: str = "optional_emit"):
    created = local_env.client.post(
        "/api/v1/fiscal/contexts",
        headers=local_env.alpha_headers(**{"Idempotency-Key": "tax-engine-context-001"}),
        json={"code":"MATRIZ-ENGINE","establishment_name":"Matriz Engine","cnpj":"12.345.678/0001-95"},
    )
    assert created.status_code == 201, created.text
    context = created.json()
    version = local_env.client.post(
        f"/api/v1/fiscal/contexts/{context['id']}/versions",
        headers=local_env.alpha_headers(**{"Idempotency-Key":"tax-engine-context-version-001"}),
        json={
            "tax_regime":"lucro_presumido","uf":"BA","municipality_code":"2927408","valid_from":"2026-01-01",
            "environment":"homologation","rtc_mode":rtc_mode,"ruleset_version":"ENGINE-2026.1",
            "scopes":[{"operation_type":"sale","item_kind":"product","recipient_scope":"company","document_type":"NF-e"},
                      {"operation_type":"service_billing","item_kind":"service","recipient_scope":"company","document_type":"NFS-e"}],
            "expected_context_version":1,
        },
    )
    assert version.status_code == 201, version.text
    published = local_env.client.post(
        f"/api/v1/fiscal/contexts/{context['id']}/versions/{version.json()['id']}/publish",
        headers=local_env.alpha_headers(**{"Idempotency-Key":"tax-engine-context-publish-001"}),
        json={"expected_context_version":2,"expected_version":1,"reason":"Contexto do golden test tributário."},
    )
    assert published.status_code == 200, published.text
    return context


def _create_rule(local_env, context_id: str, *, code: str, operation_type: str, item_kind: str, components: list[dict]):
    created = local_env.client.post(
        "/api/v1/fiscal/tax-rule-sets",
        headers=local_env.alpha_headers(**{"Idempotency-Key": f"ruleset-{code.lower()}-001"}),
        json={
            "fiscal_context_id":context_id,"code":code,"name":f"Regra {code}","establishment_code":"MATRIZ-ENGINE",
            "operation_type":operation_type,"item_kind":item_kind,"tax_regime":"lucro_presumido","rtc_mode":"optional_emit","priority":500,
        },
    )
    assert created.status_code == 201, created.text
    replay = local_env.client.post(
        "/api/v1/fiscal/tax-rule-sets",
        headers=local_env.alpha_headers(**{"Idempotency-Key": f"ruleset-{code.lower()}-001"}),
        json={
            "fiscal_context_id":context_id,"code":code,"name":f"Regra {code}","establishment_code":"MATRIZ-ENGINE",
            "operation_type":operation_type,"item_kind":item_kind,"tax_regime":"lucro_presumido","rtc_mode":"optional_emit","priority":500,
        },
    )
    assert replay.status_code == 201 and replay.json()["id"] == created.json()["id"]
    version = local_env.client.post(
        f"/api/v1/fiscal/tax-rule-sets/{created.json()['id']}/versions",
        headers=local_env.alpha_headers(**{"Idempotency-Key": f"ruleversion-{code.lower()}-001"}),
        json={
            "version_label":"2026.1","valid_from":"2026-01-01","source_name":"golden fixture local",
            "source_reference":"fixture://fiscal/golden/2026.1","legal_basis":["fixture técnica para validação do motor; não é fonte legal"],
            "components":components,"expected_rule_set_version":1,
        },
    )
    assert version.status_code == 201, version.text
    published = local_env.client.post(
        f"/api/v1/fiscal/tax-rule-sets/{created.json()['id']}/versions/{version.json()['id']}/publish",
        headers=local_env.alpha_headers(**{"Idempotency-Key": f"rulepublish-{code.lower()}-001"}),
        json={"expected_rule_set_version":2,"expected_version":1,"reason":"Golden rule revisada."},
    )
    assert published.status_code == 200, published.text
    return created.json(), published.json()


def test_product_golden_calculation_covers_classic_and_rtc_taxes_with_explainability(local_env):
    context = _create_context(local_env)
    components = [
        {"tax":"ICMS","rate_pct":"18"},
        {"tax":"ICMS_ST","base_mode":"mva","mva_pct":"40","rate_pct":"18","deduct_tax_codes":["ICMS"]},
        {"tax":"FCP","rate_pct":"2"},
        {"tax":"IPI","rate_pct":"5"},
        {"tax":"PIS","rate_pct":"1.65"},
        {"tax":"COFINS","rate_pct":"7.6"},
        {"tax":"IBS_ESTADUAL","rate_pct":"0.1"},
        {"tax":"IBS_MUNICIPAL","rate_pct":"0.1"},
        {"tax":"CBS","rate_pct":"0.9"},
        {"tax":"IS","incidence":"zero_rate","rate_pct":"0"},
    ]
    rule_set, version = _create_rule(local_env, context["id"], code="VENDA-PRODUTO-2026", operation_type="sale", item_kind="product", components=components)
    response = local_env.client.post(
        "/api/v1/fiscal/tax-calculations/simulate",
        headers=local_env.alpha_headers(**{"Idempotency-Key":"golden-product-calc-001"}),
        json={
            "fiscal_context_id":context["id"],"establishment_code":"MATRIZ-ENGINE","operation_type":"sale","item_kind":"product",
            "occurred_on":"2026-08-10","amount":"1000.00","quantity":"2","recipient_scope":"company","document_type":"NF-e",
            "expected_taxes":{"ICMS":"180.00","ICMS_ST":"72.00","FCP":"20.00","IPI":"50.00","PIS":"16.50","COFINS":"76.00","IBS_ESTADUAL":"1.00","IBS_MUNICIPAL":"1.00","CBS":"9.00","IS":"0.00"},
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["tax_total"] == "425.50"
    assert body["taxes"]["ICMS_ST"]["base"] == "1400.00"
    assert body["taxes"]["ICMS_ST"]["amount"] == "72.00"
    assert body["taxes"]["IS"]["incidence"] == "zero_rate" and body["taxes"]["IS"]["amount"] == "0.00"
    assert body["divergences"] == []
    assert len(body["snapshot_sha256"]) == 64
    assert body["rule_set"]["id"] == rule_set["id"] and body["rule_set"]["version"]["id"] == version["id"]
    assert body["explainability"]["source_sha256"] == version["source_sha256"]
    replay = local_env.client.post(
        "/api/v1/fiscal/tax-calculations/simulate",
        headers=local_env.alpha_headers(**{"Idempotency-Key":"golden-product-calc-001"}),
        json={
            "fiscal_context_id":context["id"],"establishment_code":"MATRIZ-ENGINE","operation_type":"sale","item_kind":"product",
            "occurred_on":"2026-08-10","amount":"1000.00","quantity":"2","recipient_scope":"company","document_type":"NF-e",
            "expected_taxes":{"ICMS":"180.00","ICMS_ST":"72.00","FCP":"20.00","IPI":"50.00","PIS":"16.50","COFINS":"76.00","IBS_ESTADUAL":"1.00","IBS_MUNICIPAL":"1.00","CBS":"9.00","IS":"0.00"},
        },
    )
    assert replay.status_code == 201 and replay.json()["calculation_id"] == body["calculation_id"]
    fetched = local_env.client.get(f"/api/v1/fiscal/tax-calculations/{body['calculation_id']}", headers=local_env.alpha_headers())
    assert fetched.status_code == 200 and fetched.json()["snapshot_sha256"] == body["snapshot_sha256"]
    beta = local_env.client.get(f"/api/v1/fiscal/tax-calculations/{body['calculation_id']}", headers=local_env.beta_headers())
    assert beta.status_code == 404


def test_incidence_reduction_deferral_suspension_monophase_and_divergence(local_env):
    context = _create_context(local_env)
    components = [
        {"tax":"ISS","rate_pct":"5","base_reduction_pct":"20"},
        {"tax":"PIS","incidence":"deferred","rate_pct":"2","deferral_pct":"50"},
        {"tax":"COFINS","incidence":"suspended","rate_pct":"3","suspension_pct":"100"},
        {"tax":"CBS","incidence":"monophase","monophase_amount_per_unit":"1.25"},
        {"tax":"IBS_ESTADUAL","incidence":"immune","rate_pct":"10"},
        {"tax":"IBS_MUNICIPAL","incidence":"non_incident","rate_pct":"10"},
    ]
    _create_rule(local_env, context["id"], code="SERVICO-2026", operation_type="service_billing", item_kind="service", components=components)
    response = local_env.client.post(
        "/api/v1/fiscal/tax-calculations/simulate",
        headers=local_env.alpha_headers(**{"Idempotency-Key":"golden-service-calc-001"}),
        json={
            "fiscal_context_id":context["id"],"establishment_code":"MATRIZ-ENGINE","operation_type":"service_billing","item_kind":"service",
            "occurred_on":"2026-08-10","amount":"500.00","quantity":"4","recipient_scope":"company","document_type":"NFS-e",
            "expected_taxes":{"ISS":"19.00"},
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["taxes"]["ISS"]["base"] == "400.00" and body["taxes"]["ISS"]["amount"] == "20.00"
    assert body["taxes"]["PIS"]["gross_amount"] == "10.00" and body["taxes"]["PIS"]["deferred_amount"] == "5.00" and body["taxes"]["PIS"]["amount"] == "5.00"
    assert body["taxes"]["COFINS"]["amount"] == "0.00" and body["taxes"]["COFINS"]["suspended_amount"] == "15.00"
    assert body["taxes"]["CBS"]["amount"] == "5.00"
    assert body["taxes"]["IBS_ESTADUAL"]["amount"] == "0.00" and body["taxes"]["IBS_MUNICIPAL"]["amount"] == "0.00"
    assert body["tax_total"] == "30.00"
    assert body["divergences"] == [{"tax":"ISS","expected":"19.00","actual":"20.00","difference":"1.00"}]
    store = local_env.client.app.state.data_router.tenant_store(local_env.alpha_tenant["id"])
    assert store.scalar("SELECT COUNT(*) FROM outbox_events WHERE tenant_id=? AND event_type='FiscalTaxDivergenceDetected'", (local_env.alpha_tenant["id"],)) == 1
    assert store.scalar("SELECT COUNT(*) FROM audit_log WHERE tenant_id=? AND aggregate_type='fiscal_tax_calculation'", (local_env.alpha_tenant["id"],)) == 1


def test_rule_versions_are_effective_non_overlapping_and_immutable_by_publication(local_env):
    context = _create_context(local_env)
    rule_set, version = _create_rule(local_env, context["id"], code="PERIOD-2026", operation_type="sale", item_kind="product", components=[{"tax":"ICMS","rate_pct":"18"}])
    detail = local_env.client.get(f"/api/v1/fiscal/tax-rule-sets/{rule_set['id']}", headers=local_env.alpha_headers())
    assert detail.status_code == 200 and detail.json()["versions"][0]["status"] == "published"
    overlap = local_env.client.post(
        f"/api/v1/fiscal/tax-rule-sets/{rule_set['id']}/versions",
        headers=local_env.alpha_headers(**{"Idempotency-Key":"overlap-version-001"}),
        json={"version_label":"2026.2","valid_from":"2026-06-01","source_name":"fixture","components":[{"tax":"ICMS","rate_pct":"19"}],"expected_rule_set_version":3},
    )
    assert overlap.status_code == 201, overlap.text
    publish = local_env.client.post(
        f"/api/v1/fiscal/tax-rule-sets/{rule_set['id']}/versions/{overlap.json()['id']}/publish",
        headers=local_env.alpha_headers(**{"Idempotency-Key":"overlap-publish-001"}),
        json={"expected_rule_set_version":4,"expected_version":1,"reason":"Teste de sobreposição."},
    )
    assert publish.status_code == 409 and publish.json()["code"] == "FISCAL_TAX_RULE_PERIOD_OVERLAP"
