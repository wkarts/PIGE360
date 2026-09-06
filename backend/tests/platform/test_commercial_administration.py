from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

from conftest import ALPHA_HOST


def _idem(local_env, key: str) -> dict[str, str]:
    return local_env.platform_headers(**{"Idempotency-Key": key})


def _create_partner(local_env, key: str = "partner-create-001", code: str = "norte-educacao"):
    return local_env.client.post(
        "/api/v1/platform/commercial/partners",
        headers=_idem(local_env, key),
        json={
            "code": code,
            "legal_name": "Norte Educação e Tecnologia Ltda.",
            "trade_name": "Norte Educação",
            "contact_email": "contato@norte.example.com",
            "notes": "Canal regional autorizado pela administração.",
        },
    )


def _create_plan(local_env, key: str = "plan-create-001", code: str = "escola-pro"):
    return local_env.client.post(
        "/api/v1/platform/commercial/plans",
        headers=_idem(local_env, key),
        json={
            "code": code,
            "name": "Escola Pro",
            "description": "Plano operacional para instituições de médio porte.",
            "currency": "BRL",
            "billing_interval": "monthly",
            "price_minor": 49900,
            "features": {"analytics": True, "custom_domain": True},
            "limits": {"students": 1000, "storage_gib": 50},
        },
    )


def test_commercial_routes_are_control_plane_only_and_writes_require_idempotency(local_env):
    denied = local_env.client.get(
        "/api/v1/platform/commercial/plans",
        headers={"host": ALPHA_HOST, "Authorization": f"Bearer {local_env.alpha_token}"},
    )
    assert denied.status_code in {403, 404}, denied.text

    missing_key = local_env.client.post(
        "/api/v1/platform/commercial/partners",
        headers=local_env.platform_headers(),
        json={
            "code": "sem-chave",
            "legal_name": "Parceiro sem chave Ltda.",
            "trade_name": "Sem Chave",
        },
    )
    assert missing_key.status_code == 422, missing_key.text


def test_concurrent_idempotency_replays_one_committed_partner(local_env):
    barrier = Barrier(2)

    def create():
        barrier.wait(timeout=5)
        return _create_partner(local_env, key="partner-create-concurrent", code="centro-educacao")

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = [future.result() for future in (executor.submit(create), executor.submit(create))]

    assert [response.status_code for response in responses] == [201, 201]
    assert responses[0].json()["id"] == responses[1].json()["id"]
    control = local_env.client.app.state.data_router.control
    partner_id = responses[0].json()["id"]
    assert control.scalar(
        "SELECT COUNT(*) AS n FROM commercial_partners WHERE id=?", (partner_id,)
    ) == 1
    assert control.scalar(
        "SELECT COUNT(*) AS n FROM outbox_events WHERE aggregate_id=? AND event_type='CommercialPartnerCreated'",
        (partner_id,),
    ) == 1


def test_partner_lifecycle_link_and_replay_are_audited(local_env):
    created = _create_partner(local_env)
    assert created.status_code == 201, created.text
    partner = created.json()

    replay = _create_partner(local_env)
    assert replay.status_code == 201, replay.text
    assert replay.json() == partner
    control = local_env.client.app.state.data_router.control
    assert control.scalar("SELECT COUNT(*) AS n FROM commercial_partners WHERE code=?", (partner["code"],)) == 1

    conflict = _create_partner(local_env, code="outro-codigo")
    assert conflict.status_code == 409, conflict.text
    assert conflict.json()["code"] == "IDEMPOTENCY_KEY_REUSED"

    updated = local_env.client.patch(
        f"/api/v1/platform/commercial/partners/{partner['id']}",
        headers=_idem(local_env, "partner-update-001"),
        json={
            "expected_version": 1,
            "reason": "Atualização cadastral confirmada pelo responsável",
            "trade_name": "Norte Educação Regional",
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["trade_name"] == "Norte Educação Regional"
    assert updated.json()["version"] == 2

    tenant_id = local_env.alpha_tenant["id"]
    linked = local_env.client.put(
        f"/api/v1/platform/commercial/partners/{partner['id']}/tenants/{tenant_id}",
        headers=_idem(local_env, "partner-link-alpha-001"),
        json={"reason": "Contrato de parceria aprovado pelo Control Plane"},
    )
    assert linked.status_code == 200, linked.text
    assert linked.json()["changed"] is True

    listed = local_env.client.get(
        f"/api/v1/platform/commercial/partners/{partner['id']}",
        headers=local_env.platform_headers(),
    )
    assert listed.status_code == 200, listed.text
    assert listed.json()["tenant_count"] == 1
    assert listed.json()["tenants"][0]["id"] == tenant_id

    suspended = local_env.client.post(
        f"/api/v1/platform/commercial/partners/{partner['id']}/suspend",
        headers=_idem(local_env, "partner-suspend-001"),
        json={"expected_version": 2, "reason": "Revisão contratual solicitada pela administração"},
    )
    assert suspended.status_code == 200, suspended.text
    assert suspended.json()["status"] == "suspended"

    blocked_link = local_env.client.put(
        f"/api/v1/platform/commercial/partners/{partner['id']}/tenants/{local_env.beta_tenant['id']}",
        headers=_idem(local_env, "partner-link-beta-001"),
        json={"reason": "Tentativa durante suspensão contratual do parceiro"},
    )
    assert blocked_link.status_code == 409, blocked_link.text
    assert blocked_link.json()["code"] == "COMMERCIAL_PARTNER_INACTIVE"

    blocked_archive = local_env.client.request(
        "DELETE",
        f"/api/v1/platform/commercial/partners/{partner['id']}",
        headers=_idem(local_env, "partner-archive-001"),
        json={"expected_version": 3, "reason": "Encerramento formal do relacionamento comercial"},
    )
    assert blocked_archive.status_code == 409, blocked_archive.text
    assert blocked_archive.json()["code"] == "COMMERCIAL_PARTNER_HAS_TENANTS"

    unlinked = local_env.client.request(
        "DELETE",
        f"/api/v1/platform/commercial/partners/{partner['id']}/tenants/{tenant_id}",
        headers=_idem(local_env, "partner-unlink-alpha-001"),
        json={"reason": "Tenant transferido para atendimento direto da plataforma"},
    )
    assert unlinked.status_code == 200, unlinked.text
    assert unlinked.json()["changed"] is True

    archived = local_env.client.request(
        "DELETE",
        f"/api/v1/platform/commercial/partners/{partner['id']}",
        headers=_idem(local_env, "partner-archive-002"),
        json={"expected_version": 3, "reason": "Encerramento formal do relacionamento comercial"},
    )
    assert archived.status_code == 200, archived.text
    assert archived.json()["status"] == "archived"

    actions = {
        row["action"]
        for row in control.fetch_all(
            "SELECT action FROM audit_log WHERE aggregate_id IN (?,?)",
            (partner["id"], tenant_id),
        )
    }
    assert {
        "commercial_partner_created",
        "commercial_partner_updated",
        "commercial_partner_suspended",
        "commercial_partner_archived",
        "commercial_partner_tenant_linked",
        "commercial_partner_tenant_unlinked",
    }.issubset(actions)
    events = {
        row["event_type"]
        for row in control.fetch_all(
            "SELECT event_type FROM outbox_events WHERE aggregate_id IN (?,?)",
            (partner["id"], tenant_id),
        )
    }
    assert "CommercialPartnerCreated" in events
    assert "TenantLinkedToCommercialPartner" in events


def test_plan_subscription_usage_and_entitlements_are_consistent(local_env):
    created = _create_plan(local_env)
    assert created.status_code == 201, created.text
    plan = created.json()
    tenant_id = local_env.alpha_tenant["id"]

    subscription_payload = {
        "expected_version": 0,
        "plan_id": plan["id"],
        "status": "active",
        "starts_at": "2026-09-01T00:00:00Z",
        "current_period_end": "2026-10-01T00:00:00Z",
        "cancel_at_period_end": False,
        "reason": "Contratação aprovada para o novo período comercial",
    }
    subscription = local_env.client.put(
        f"/api/v1/platform/commercial/tenants/{tenant_id}/subscription",
        headers=_idem(local_env, "subscription-alpha-001"),
        json=subscription_payload,
    )
    assert subscription.status_code == 200, subscription.text
    assert subscription.json()["billing_mode"] == "manual"
    assert subscription.json()["automatic_charging"] is False

    replay = local_env.client.put(
        f"/api/v1/platform/commercial/tenants/{tenant_id}/subscription",
        headers=_idem(local_env, "subscription-alpha-001"),
        json=subscription_payload,
    )
    assert replay.status_code == 200, replay.text
    assert replay.json() == subscription.json()

    usage = local_env.client.put(
        f"/api/v1/platform/commercial/tenants/{tenant_id}/usage/2026-09",
        headers=_idem(local_env, "usage-alpha-2026-09-manual"),
        json={
            "expected_version": 0,
            "source": "manual",
            "metrics": {"students": 725, "storage_gib": 12},
            "reason": "Consolidação administrativa do fechamento mensal",
        },
    )
    assert usage.status_code == 200, usage.text
    assert usage.json()["version"] == 1

    entitlements = local_env.client.get(
        f"/api/v1/platform/commercial/tenants/{tenant_id}/entitlements",
        headers=local_env.platform_headers(),
        params={"period": "2026-09"},
    )
    assert entitlements.status_code == 200, entitlements.text
    body = entitlements.json()
    assert body["entitlements"]["enabled"] is True
    assert body["entitlements"]["features"]["analytics"] is True
    assert body["entitlements"]["remaining"] == {"students": 275, "storage_gib": 38}
    assert body["commercial_policy"] == {
        "billing_mode": "manual",
        "automatic_charging": False,
        "external_billing_provider": None,
        "usage_collection": "administrative_snapshots",
        "entitlement_enforcement": "informational",
    }

    updated = local_env.client.patch(
        f"/api/v1/platform/commercial/plans/{plan['id']}",
        headers=_idem(local_env, "plan-update-001"),
        json={
            "expected_version": 1,
            "reason": "Ampliação de capacidade aprovada para o catálogo",
            "limits": {"students": 1200, "storage_gib": 80},
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["version"] == 2

    stale = local_env.client.patch(
        f"/api/v1/platform/commercial/plans/{plan['id']}",
        headers=_idem(local_env, "plan-update-stale-001"),
        json={
            "expected_version": 1,
            "reason": "Tentativa com versão antiga deve ser recusada",
            "name": "Nome obsoleto",
        },
    )
    assert stale.status_code == 409, stale.text
    assert stale.json()["code"] == "COMMERCIAL_PLAN_VERSION_CONFLICT"

    null_required = local_env.client.patch(
        f"/api/v1/platform/commercial/plans/{plan['id']}",
        headers=_idem(local_env, "plan-update-null-001"),
        json={
            "expected_version": 2,
            "reason": "Campo obrigatório nulo deve ser recusado na fronteira",
            "name": None,
        },
    )
    assert null_required.status_code == 422, null_required.text

    blocked_archive = local_env.client.request(
        "DELETE",
        f"/api/v1/platform/commercial/plans/{plan['id']}",
        headers=_idem(local_env, "plan-archive-blocked-001"),
        json={"expected_version": 2, "reason": "Arquivo solicitado durante assinatura ativa"},
    )
    assert blocked_archive.status_code == 409, blocked_archive.text
    assert blocked_archive.json()["code"] == "COMMERCIAL_PLAN_HAS_SUBSCRIPTIONS"

    canceled = local_env.client.put(
        f"/api/v1/platform/commercial/tenants/{tenant_id}/subscription",
        headers=_idem(local_env, "subscription-alpha-cancel-001"),
        json={**subscription_payload, "expected_version": 1, "status": "canceled", "reason": "Cancelamento confirmado pelo responsável contratual"},
    )
    assert canceled.status_code == 200, canceled.text
    assert canceled.json()["status"] == "canceled"

    archived = local_env.client.request(
        "DELETE",
        f"/api/v1/platform/commercial/plans/{plan['id']}",
        headers=_idem(local_env, "plan-archive-allowed-001"),
        json={"expected_version": 2, "reason": "Catálogo legado encerrado após cancelamento dos vínculos"},
    )
    assert archived.status_code == 200, archived.text
    assert archived.json()["status"] == "archived"

    resurrect = local_env.client.patch(
        f"/api/v1/platform/commercial/plans/{plan['id']}",
        headers=_idem(local_env, "plan-resurrect-forbidden-001"),
        json={
            "expected_version": 3,
            "reason": "Plano arquivado não pode voltar pelo update genérico",
            "status": "active",
        },
    )
    assert resurrect.status_code == 409, resurrect.text
    assert resurrect.json()["code"] == "COMMERCIAL_PLAN_ARCHIVED"

    suspended_on_archived = local_env.client.put(
        f"/api/v1/platform/commercial/tenants/{tenant_id}/subscription",
        headers=_idem(local_env, "subscription-archived-suspended-forbidden"),
        json={
            **subscription_payload,
            "expected_version": 2,
            "status": "suspended",
            "reason": "Plano arquivado não pode reabrir uma assinatura operacional",
        },
    )
    assert suspended_on_archived.status_code == 409, suspended_on_archived.text
    assert suspended_on_archived.json()["code"] == "COMMERCIAL_PLAN_ARCHIVED"

    replacement = _create_plan(local_env, key="plan-replacement-create", code="escola-next")
    assert replacement.status_code == 201, replacement.text
    moved = local_env.client.put(
        f"/api/v1/platform/commercial/tenants/{tenant_id}/subscription",
        headers=_idem(local_env, "subscription-move-active-plan"),
        json={
            **subscription_payload,
            "expected_version": 2,
            "plan_id": replacement.json()["id"],
            "status": "active",
            "reason": "Migração contratual para o plano substituto ativo",
        },
    )
    assert moved.status_code == 200, moved.text

    cross_plan_cancel = local_env.client.put(
        f"/api/v1/platform/commercial/tenants/{tenant_id}/subscription",
        headers=_idem(local_env, "subscription-cross-plan-archive"),
        json={
            **subscription_payload,
            "expected_version": 3,
            "status": "canceled",
            "reason": "Plano arquivado não pode substituir outro durante cancelamento",
        },
    )
    assert cross_plan_cancel.status_code == 409, cross_plan_cancel.text
    assert cross_plan_cancel.json()["code"] == "COMMERCIAL_PLAN_ARCHIVED"


def test_usage_snapshot_enforces_version_and_valid_period(local_env):
    tenant_id = local_env.beta_tenant["id"]
    first = local_env.client.put(
        f"/api/v1/platform/commercial/tenants/{tenant_id}/usage/2026-08",
        headers=_idem(local_env, "usage-beta-2026-08-001"),
        json={
            "expected_version": 0,
            "source": "operations",
            "metrics": {"students": 120},
            "reason": "Importação consolidada do sistema operacional interno",
        },
    )
    assert first.status_code == 200, first.text

    stale = local_env.client.put(
        f"/api/v1/platform/commercial/tenants/{tenant_id}/usage/2026-08",
        headers=_idem(local_env, "usage-beta-2026-08-stale"),
        json={
            "expected_version": 0,
            "source": "operations",
            "metrics": {"students": 130},
            "reason": "Tentativa concorrente com uma versão desatualizada",
        },
    )
    assert stale.status_code == 409, stale.text
    assert stale.json()["code"] == "COMMERCIAL_USAGE_VERSION_CONFLICT"

    invalid_period = local_env.client.put(
        f"/api/v1/platform/commercial/tenants/{tenant_id}/usage/2026-13",
        headers=_idem(local_env, "usage-beta-invalid-period"),
        json={
            "expected_version": 0,
            "source": "operations",
            "metrics": {"students": 130},
            "reason": "Período inválido deve ser recusado na fronteira HTTP",
        },
    )
    assert invalid_period.status_code == 422, invalid_period.text

    invalid_metric = local_env.client.put(
        f"/api/v1/platform/commercial/tenants/{tenant_id}/usage/2026-09",
        headers=_idem(local_env, "usage-beta-invalid-metric"),
        json={
            "expected_version": 0,
            "source": "operations",
            "metrics": {"students": True},
            "reason": "Booleano não pode ser convertido silenciosamente em consumo",
        },
    )
    assert invalid_metric.status_code == 422, invalid_metric.text


def test_commercial_schema_and_migration_are_additive():
    root = Path(__file__).resolve().parents[2]
    schema = (root / "app/shared/database/control_schema.sql").read_text(encoding="utf-8")
    migration = (root / "alembic_control/versions/0007_commercial_administration.py").read_text(encoding="utf-8")
    for table in (
        "commercial_partners",
        "commercial_partner_tenants",
        "commercial_plans",
        "commercial_subscriptions",
        "commercial_usage_snapshots",
        "commercial_idempotency_records",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in schema
        assert f"CREATE TABLE IF NOT EXISTS {table}" in migration
    assert 'revision = "0007_commercial_administration"' in migration
    assert 'down_revision = "0006_operational_control"' in migration
    assert "for statement in _statements(DDL)" in migration
    assert "ALTER TABLE platform_tenants" not in migration


def test_commercial_json_never_contains_connect_reference_branding(local_env):
    partner = _create_partner(local_env, key="partner-branding-isolation", code="sul-educacao")
    plan = _create_plan(local_env, key="plan-branding-isolation", code="rede-escolar")
    assert partner.status_code == 201, partner.text
    assert plan.status_code == 201, plan.text
    serialized = json.dumps({"partner": partner.json(), "plan": plan.json()}, ensure_ascii=False).lower()
    assert "connect|api" not in serialized
    assert "connect-api" not in serialized
