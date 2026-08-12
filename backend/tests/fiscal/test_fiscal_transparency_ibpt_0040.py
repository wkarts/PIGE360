from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

from app.shared.domain.ids import iso_now
from app.worker import schedule_ibpt_for_active_tenants
from tests.fiscal.test_fiscal_document_routing_assembly import _context, _financial_service_order, _schemas


def _create_ibpt_profile(local_env, *, mode: str, sync_enabled: bool, fallback_enabled: bool = True, key: str = "ibpt-profile-0040"):
    created = local_env.client.post(
        "/api/v1/fiscal/ibpt/provider-profiles",
        headers=local_env.alpha_headers(**{"Idempotency-Key": key}),
        json={
            "provider_code": "wwsoftwares",
            "mode": mode,
            "valid_from": "2026-01-01",
            "sync_enabled": sync_enabled,
            "fallback_enabled": fallback_enabled,
            "fallback_max_age_days": 90,
            "stale_after_days": 120,
            "base_url": "https://ibpt.wwsoftwares.com.br",
            "uf_path": "/tabela/ibpt/{uf}",
            "notes": "Perfil IBPT 0040 de teste local.",
        },
    )
    assert created.status_code == 201, created.text
    published = local_env.client.post(
        f"/api/v1/fiscal/ibpt/provider-profiles/{created.json()['id']}/publish",
        headers=local_env.alpha_headers(),
        json={"expected_version": created.json()["version"], "reason": "Publicação do perfil IBPT 0040."},
    )
    assert published.status_code == 200, published.text
    return published.json()


def test_ibpt_profile_is_versioned_and_scheduler_selects_only_remote_sync_tenant(local_env):
    profile = _create_ibpt_profile(local_env, mode="remote_sync", sync_enabled=True)
    assert profile["state"] == "published" and profile["mode"] == "remote_sync"

    router = local_env.client.app.state.data_router
    scheduled = schedule_ibpt_for_active_tenants(router=router)
    assert scheduled["status"] == "queued"
    assert scheduled["tenants"] == 2
    assert scheduled["eligible_tenants"] == 1
    assert scheduled["skipped_tenants"] == 1
    assert scheduled["runs"] == 27
    alpha_store = router.tenant_store(local_env.alpha_tenant["id"])
    beta_store = router.tenant_store(local_env.beta_tenant["id"])
    assert alpha_store.scalar("SELECT COUNT(*) FROM ibpt_sync_runs WHERE tenant_id=?", (local_env.alpha_tenant["id"],)) == 27
    assert beta_store.scalar("SELECT COUNT(*) FROM ibpt_sync_runs WHERE tenant_id=?", (local_env.beta_tenant["id"],)) == 0

    # Repetição não cria segunda fila por UF enquanto os runs estiverem pendentes.
    again = schedule_ibpt_for_active_tenants(router=router)
    assert again["eligible_tenants"] == 1
    assert alpha_store.scalar("SELECT COUNT(*) FROM ibpt_sync_runs WHERE tenant_id=?", (local_env.alpha_tenant["id"],)) == 27


def test_document_transparency_separates_real_taxes_and_ibpt_with_controlled_fallback(local_env):
    context, fiscal_profile = _context(local_env)
    _schemas(local_env)
    profile = _create_ibpt_profile(local_env, mode="local_snapshot", sync_enabled=False, key="ibpt-profile-local-0040")
    tenant_id = local_env.alpha_tenant["id"]
    store = local_env.client.app.state.data_router.tenant_store(tenant_id)
    now = iso_now()
    with store.transaction() as conn:
        conn.execute(
            "INSERT INTO ibpt_snapshots(id,tenant_id,uf,source_url,sha256,storage_key,rows_count,source_version,effective_from,effective_to,state,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            ("snap-active-0040", tenant_id, "BA", "fixture://active", "a" * 64, "fixture/active.csv", 1, "26.1", "2026-01-01", "2026-12-31", "active", now),
        )
        conn.execute(
            "INSERT INTO ibpt_rates(id,tenant_id,snapshot_id,uf,code,ex,item_type,description,national_federal,imported_federal,state_rate,municipal_rate,effective_from,effective_to,source_version,source_name,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("rate-active-other", tenant_id, "snap-active-0040", "BA", "99999999", "", "0", "Outro", "1", "1", "1", "1", "2026-01-01", "2026-12-31", "26.1", "IBPT", now),
        )
        conn.execute(
            "INSERT INTO ibpt_snapshots(id,tenant_id,uf,source_url,sha256,storage_key,rows_count,source_version,effective_from,effective_to,state,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            ("snap-fallback-0040", tenant_id, "BA", "fixture://fallback", "b" * 64, "fixture/fallback.csv", 1, "26.0", "2026-01-01", "2026-12-31", "superseded", now),
        )
        conn.execute(
            "INSERT INTO ibpt_rates(id,tenant_id,snapshot_id,uf,code,ex,item_type,description,national_federal,imported_federal,state_rate,municipal_rate,effective_from,effective_to,source_version,source_name,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("rate-fallback-target", tenant_id, "snap-fallback-0040", "BA", "01012100", "", "0", "Produto", "10", "15", "20", "2", "2026-01-01", "2026-12-31", "26.0", "IBPT", now),
        )

    assembly = local_env.client.post(
        "/api/v1/fiscal/document-assemblies",
        headers=local_env.alpha_headers(**{"Idempotency-Key": "assembly-tax-transparency-0040"}),
        json={
            "fiscal_context_id": context["id"],
            "fiscal_profile_id": fiscal_profile["id"],
            "source_type": "manual",
            "source_id": "sale-transparency-0040",
            "occurred_on": "2026-08-11",
            "operation_type": "sale",
            "recipient_scope": "individual",
            "channel": "pos",
            "destination_uf": "BA",
            "trigger_type": "manual",
            "recipient": {"name": "Consumidor", "document": "12345678909", "uf": "BA"},
            "items": [{
                "line_id": "line-1", "item_kind": "product", "code": "P1", "description": "Produto IBPT",
                "quantity": "1", "unit_price": "100.00", "discount": "0", "total_amount": "100.00",
                "classification": {"ncm": "01012100", "origin": "national"},
            }],
            "request_emission": True,
            "metadata": {"real_taxes": {"ICMS": "18.00", "PIS": "1.65"}},
        },
    )
    assert assembly.status_code == 201, assembly.text
    body = assembly.json()
    assert body["state"] == "emission_requested"
    transparency_in_build = body["builds"][0]["tax_transparency"]
    assert transparency_in_build["vTotTrib"] == "32.00"
    assert transparency_in_build["approximate_ibpt"]["tax_calculation_source"] is False
    assert transparency_in_build["approximate_ibpt"]["items"][0]["source_state"] == "fallback"
    assert transparency_in_build["ibpt_provider_profile_id"] == profile["id"]

    document_id = body["documents"][0]["id"]
    response = local_env.client.get(f"/api/v1/fiscal/documents/{document_id}/transparency", headers=local_env.alpha_headers())
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["real_taxes"] == {"ICMS": "18.00", "PIS": "1.65"}
    assert data["approximate_ibpt"]["purpose"] == "transparencia_vtottrib"
    assert data["approximate_ibpt"]["tax_calculation_source"] is False
    assert data["vTotTrib"] == "32"


def test_manifestation_and_configurable_fiscal_reversal_accounts(local_env):
    context, profile, policy, ids = _financial_service_order(local_env, suffix="0040-accounts", paid=False)
    tenant_id = local_env.alpha_tenant["id"]
    store = local_env.client.app.state.data_router.tenant_store(tenant_id)
    row = store.fetch_one("SELECT settings_json FROM fiscal_document_routing_policies WHERE tenant_id=? AND id=?", (tenant_id, policy["id"]))
    settings = json.loads(row["settings_json"])
    settings.update({"fiscal_reversal_debit_account": "fiscal_revenue_reversal", "fiscal_reversal_credit_account": "fiscal_receivable_reversal"})
    store.execute("UPDATE fiscal_document_routing_policies SET settings_json=? WHERE tenant_id=? AND id=?", (json.dumps(settings), tenant_id, policy["id"]))

    response = local_env.client.post(
        "/api/v1/fiscal/document-assemblies",
        headers=local_env.alpha_headers(**{"Idempotency-Key": "assembly-fin-0040-accounts"}),
        json={
            "fiscal_context_id": context["id"], "fiscal_profile_id": profile["id"],
            "source_type": "service_order", "source_id": ids["order"], "occurred_on": "2026-08-11",
            "operation_type": "service", "recipient_scope": "individual", "channel": "service",
            "trigger_type": "manual", "recipient": {"name": "Responsável", "document": "12345678909", "uf": "BA"},
            "request_emission": True,
        },
    )
    assert response.status_code == 201, response.text
    document_id = response.json()["documents"][0]["id"]

    # A manifestação usa o lifecycle já existente: provider configurado + documento autorizado.
    connection_id = "fiscal-provider-0040"
    now = iso_now()
    with store.transaction() as conn:
        conn.execute(
            "INSERT INTO integration_connections(id,tenant_id,provider,name,environment,capabilities_json,config_json,state,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (connection_id, tenant_id, "SefazNfeProvider", "Provider fixture", "homologation", "[]", "{}", "configured", now, now),
        )
        conn.execute("UPDATE fiscal_documents SET state='authorized',provider_connection_id=?,provider_status='authorized' WHERE tenant_id=? AND id=?", (connection_id, tenant_id, document_id))
    manifestation = local_env.client.post(
        f"/api/v1/fiscal/documents/{document_id}/events",
        headers=local_env.alpha_headers(**{"Idempotency-Key": "manifestation-0040"}),
        json={"event_type": "manifestation", "reason": "Manifestação fiscal fixture 0040.", "payload": {"manifestation": "acknowledged"}},
    )
    assert manifestation.status_code == 201, manifestation.text
    assert manifestation.json()["event_type"] == "manifestation"
    # O cenário de manifestação precisa de documento autorizado; para exercitar no mesmo
    # teste o cancelamento local/contábil, voltamos o fixture ao estado solicitado sem
    # apagar o evento de manifestação já persistido.
    store.execute("UPDATE fiscal_documents SET state='requested',provider_status='queued' WHERE tenant_id=? AND id=?", (tenant_id, document_id))

    cancelled = local_env.client.post(
        f"/api/v1/fiscal/documents/{document_id}/cancel",
        headers=local_env.alpha_headers(),
        json={"reason": "Cancelamento fiscal para validar contas configuráveis."},
    )
    assert cancelled.status_code == 200, cancelled.text
    outcome = cancelled.json()["financial_adjustment"]["outcomes"][0]
    reversal = store.fetch_one("SELECT debit_account,credit_account FROM ledger_entries WHERE tenant_id=? AND id=?", (tenant_id, outcome["ledger_entry_id"]))
    assert reversal["debit_account"] == "fiscal_revenue_reversal"
    assert reversal["credit_account"] == "fiscal_receivable_reversal"


def test_additional_versioned_catalog_kinds_and_tenant_isolation(local_env):
    kinds = ["NFSE_CORRELATION", "MUNICIPAL_CODE", "TAX_RATE", "TECHNICAL_NOTE"]
    ids = []
    for index, kind in enumerate(kinds, start=1):
        response = local_env.client.post(
            "/api/v1/fiscal/catalogs",
            headers=local_env.alpha_headers(**{"Idempotency-Key": f"catalog-0040-{index:02d}"}),
            json={"kind": kind, "name": f"Catálogo {kind}", "normalization": "upper_alnum", "metadata": {"0040": True}},
        )
        assert response.status_code == 201, response.text
        ids.append(response.json()["id"])
    alpha = local_env.client.get("/api/v1/fiscal/catalogs", headers=local_env.alpha_headers())
    beta = local_env.client.get("/api/v1/fiscal/catalogs", headers=local_env.beta_headers())
    assert alpha.status_code == 200 and beta.status_code == 200
    alpha_kinds = {row["kind"] for row in alpha.json()["items"] if row["id"] in ids}
    assert alpha_kinds == set(kinds)
    assert not ({row["id"] for row in beta.json()["items"]} & set(ids))
