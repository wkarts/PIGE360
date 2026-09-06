from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
COMPONENT = (
    ROOT
    / "apps"
    / "platform-console"
    / "src"
    / "components"
    / "OperationalAdministrationPanel.vue"
)
COMPILED_MIRROR = COMPONENT.with_suffix(".vue.js")
APP = ROOT / "apps" / "platform-console" / "src" / "App.vue"
APP_MIRROR = APP.with_suffix(".vue.js")


def test_operational_panel_uses_the_real_agent_provider_and_job_contracts():
    source = COMPONENT.read_text(encoding="utf-8")
    for contract in (
        "/platform/operations/agents",
        "/platform/operations/providers",
        "/platform/operations/jobs",
        "/revoke",
        "/cancel",
        "expected_version",
        "Idempotency-Key",
        "backup.execute",
        "restore.execute",
        "deploy.execute",
    ):
        assert contract in source


def test_operational_panel_is_honest_about_observation_and_execution_limits():
    source = COMPONENT.read_text(encoding="utf-8")
    for truth_contract in (
        "configured_not_probed",
        "external_probe_performed=false",
        "execution_started",
        "execução ainda não",
        "não afirma reatribuição automática",
        "nenhum comando é executado por esta tela",
    ):
        assert truth_contract in source


def test_agent_credential_is_one_time_copyable_and_not_persisted_in_browser_storage():
    source = COMPONENT.read_text(encoding="utf-8")
    for credential_contract in (
        "Credencial exibida uma única vez",
        "oneTimeCredential.header",
        "oneTimeCredential.token",
        "navigator.clipboard.writeText",
        "Ocultar definitivamente",
    ):
        assert credential_contract in source
    assert "localStorage" not in source
    assert "sessionStorage" not in source


def test_global_console_adds_operational_and_commercial_panels_without_replacing_surfaces():
    source = APP.read_text(encoding="utf-8")
    for panel in (
        'import CommercialAdministrationPanel from "./components/CommercialAdministrationPanel.vue"',
        'import OperationalAdministrationPanel from "./components/OperationalAdministrationPanel.vue"',
        "<OperationalAdministrationPanel",
        "<CommercialAdministrationPanel",
        '@feedback="handlePanelFeedback"',
    ):
        assert panel in source
    for existing_surface in (
        "Provisionar tenant",
        "Auditoria global",
        "Domínios",
        "Releases",
        "Central de logs",
        "Sessão de suporte",
    ):
        assert existing_surface in source


def test_generated_mirrors_include_the_same_operational_and_global_contracts():
    operational = COMPILED_MIRROR.read_text(encoding="utf-8")
    app = APP_MIRROR.read_text(encoding="utf-8")
    for contract in (
        "/platform/operations/agents",
        "/platform/operations/providers",
        "/platform/operations/jobs",
        "configured_not_probed",
        "execution_started",
        "navigator.clipboard.writeText",
    ):
        assert contract in operational
    assert "OperationalAdministrationPanel" in app
    assert "CommercialAdministrationPanel" in app
