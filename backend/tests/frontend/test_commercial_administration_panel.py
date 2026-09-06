from __future__ import annotations

from pathlib import Path


def test_commercial_administration_component_is_isolated_and_uses_control_contract():
    root = Path(__file__).resolve().parents[3]
    component = root / "apps/platform-console/src/components/CommercialAdministrationPanel.vue"
    source = component.read_text(encoding="utf-8")
    assert "defineProps" in source
    assert "Pige360SessionClient" in source
    for route in (
        "/platform/commercial/partners",
        "/platform/commercial/plans",
        "/platform/commercial/tenants/",
    ):
        assert route in source
    assert '"Idempotency-Key"' in source
    assert "automatic_charging" not in source
    assert "Cobrança automática externa: não habilitada." in source
    assert "connect|api" not in source.lower()


def test_commercial_panel_integration_is_documented_without_replacing_app_shell():
    root = Path(__file__).resolve().parents[3]
    document = (root / "docs/operations/COMMERCIAL_ADMINISTRATION.md").read_text(encoding="utf-8")
    assert "CommercialAdministrationPanel.vue" in document
    assert "sem alterar" in document
    assert "entitlement_enforcement=informational" in document
    assert "billing_mode=manual" in document


def test_current_suspended_partner_remains_selectable_only_for_existing_link_actions():
    root = Path(__file__).resolve().parents[3]
    component = root / "apps/platform-console/src/components/CommercialAdministrationPanel.vue"
    source = component.read_text(encoding="utf-8")
    for contract in (
        "selectablePartners",
        'item.status === "active" || item.id === linkedPartnerId.value',
        'selectedPartnerId.value = entitlementData.partner?.id || ""',
        'if (!unlink && partner.status !== "active")',
        "Somente parceiro ativo pode receber um novo vínculo.",
        "result.changed ? successMessage : noChangeMessage",
        "Nenhuma alteração: o tenant já estava desvinculado deste parceiro.",
    ):
        assert contract in source


def test_current_inactive_subscription_plan_remains_available_without_enabling_new_sale():
    root = Path(__file__).resolve().parents[3]
    component = root / "apps/platform-console/src/components/CommercialAdministrationPanel.vue"
    source = component.read_text(encoding="utf-8")
    for contract in (
        "selectableSubscriptionPlans",
        'item.status === "active" || item.id === currentSubscriptionPlanId.value',
        "(!isCurrentPlan && selectedPlan.status !== \"active\")",
        "Uma nova assinatura ou migração exige um plano ativo.",
        "Cancele esta assinatura ou migre para um plano ativo.",
        "(plano atual)",
    ):
        assert contract in source


def test_generated_commercial_mirror_keeps_selection_guards():
    root = Path(__file__).resolve().parents[3]
    mirror = root / "apps/platform-console/src/components/CommercialAdministrationPanel.vue.js"
    source = mirror.read_text(encoding="utf-8")
    for contract in (
        "selectablePartners",
        "linkedPartnerId",
        "selectableSubscriptionPlans",
        "currentSubscriptionPlanId",
        "result.changed ? successMessage : noChangeMessage",
    ):
        assert contract in source
