from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "apps" / "platform-console" / "src" / "App.vue"
COMPILED_MIRROR = ROOT / "apps" / "platform-console" / "src" / "App.vue.js"
STYLES = ROOT / "apps" / "platform-console" / "src" / "styles.css"


def test_platform_console_exposes_administration_without_removing_existing_surfaces():
    source = APP.read_text(encoding="utf-8")
    for existing_surface in (
        "Provisionar tenant",
        "Auditoria global",
        "Domínios",
        "Releases",
        "Central de logs",
        "Sessão de suporte",
    ):
        assert existing_surface in source
    for administrative_contract in (
        "/platform/operations/inventory",
        "/platform/users",
        "changeTenantState('suspend')",
        "changeTenantState('reactivate')",
        "/quotas",
        "/revoke",
        "Saúde e recursos",
        "Usuários da plataforma",
        "Quotas do tenant",
    ):
        assert administrative_contract in source


def test_app_factory_console_exposes_supported_products_platforms_jobs_artifacts_and_retry():
    source = APP.read_text(encoding="utf-8")
    assert "Builds nativos estão congelados" not in source
    for target in (
        "family-mobile",
        "teacher-mobile",
        "student-mobile",
        "desktop-admin",
        "pos-desktop",
        "android-apk",
        "android-aab",
        "ios-ipa-unsigned",
        "windows-x64",
        "windows-x86",
        "linux-arm64",
        "macos-apple",
    ):
        assert target in source
    for visibility_contract in ("build.jobs", "build.artifacts", "retryBuild(build)"):
        assert visibility_contract in source


def test_platform_console_generated_javascript_mirror_matches_current_admin_contract():
    source = COMPILED_MIRROR.read_text(encoding="utf-8")
    for contract in (
        "/platform/operations/inventory",
        "/platform/users",
        "/quotas",
        "android-apk",
        "windows-x64",
        "changeTenantState",
        "retryBuild",
    ):
        assert contract in source
    assert "Builds nativos estão congelados" not in source


def test_platform_console_styles_cover_new_responsive_administration_components():
    styles = STYLES.read_text(encoding="utf-8")
    for selector in (".quota-grid", ".build-selection", ".build-card", ".job-grid", ".support-session"):
        assert selector in styles
