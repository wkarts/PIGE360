from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[3]


def test_api_healthcheck_resolves_the_platform_host() -> None:
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")

    assert "console.platform.local" in compose
    assert "/api/v1/health/live" in compose


def test_runtime_image_workflow_runs_compose_smoke_after_build() -> None:
    workflow = (ROOT / ".github/workflows/20-application-images.yml").read_text(encoding="utf-8")
    release = (ROOT / ".github/workflows/50-release.yml").read_text(encoding="utf-8")
    smoke = ROOT / "scripts/ci/smoke-compose-homologation.sh"

    assert smoke.is_file()
    assert "build-runtime-images.sh all" in workflow
    assert "smoke-compose-homologation.sh" in workflow
    assert "smoke-compose-homologation.sh" in release
    assert "runtime_images:" in release
    assert "needs: [version, validation, runtime_images]" in release


def test_smoke_override_uses_the_runtime_images_without_rebuilding() -> None:
    override = (ROOT / "infra/compose/compose.homologation-smoke.yaml").read_text(encoding="utf-8")

    for image in ("pige360-migrations", "pige360-api", "pige360-web"):
        assert f"image: {image}:${{PIGE360_IMAGE_TAG}}" in override
    assert override.count("pull_policy: never") == 3


def test_runtime_image_build_uses_engine_builder_for_local_base_chain() -> None:
    script = (ROOT / "scripts/oci/build-runtime-images.sh").read_text(encoding="utf-8")

    assert 'engine_builder="default"' in script
    assert 'docker buildx inspect "$engine_builder"' in script
    assert '--builder "$engine_builder"' in script
    assert 'PYTHON_BASE_IMAGE=pige360-base-python:${image_tag}' in script
    assert 'API_IMAGE=pige360-api:${image_tag}' in script


def test_rabbitmq_uses_a_secret_loader_and_a_startup_grace_period() -> None:
    for name in ("compose.yaml", "infra/templates/compose.yaml.tmpl"):
        compose = yaml.safe_load((ROOT / name).read_text(encoding="utf-8"))
        rabbitmq = compose["services"]["pige360-rabbitmq"]

        assert "RABBITMQ_DEFAULT_PASS_FILE" not in rabbitmq["environment"]
        assert rabbitmq["entrypoint"] == [
            "/bin/sh",
            "-ec",
            'export RABBITMQ_DEFAULT_PASS="$$(cat /run/secrets/rabbitmq_password)"; exec docker-entrypoint.sh rabbitmq-server',
        ]
        assert rabbitmq["healthcheck"]["test"] == [
            "CMD-SHELL",
            "rabbitmq-diagnostics -q ping && rabbitmq-diagnostics -q check_running",
        ]
        assert rabbitmq["healthcheck"]["start_period"] == "45s"
        assert rabbitmq["healthcheck"]["retries"] == 12


def test_compose_smoke_keeps_service_diagnostics_after_a_startup_failure() -> None:
    smoke = (ROOT / "scripts/ci/smoke-compose-homologation.sh").read_text(encoding="utf-8")
    dockerfile = (ROOT / "infra/docker/Dockerfile.web").read_text(encoding="utf-8")

    assert "capture_startup_failure" in smoke
    assert "compose-startup-diagnostics.log" in smoke
    assert "logs --no-color --timestamps pige360-web pige360-rabbitmq" in smoke
    assert "if ! docker compose" in smoke
    assert "rm -f /etc/nginx/conf.d/default.conf" in dockerfile
    assert "RUN nginx -t" in dockerfile
    assert "ENTRYPOINT []" in dockerfile
    assert 'CMD ["nginx", "-g", "daemon off;"]' in dockerfile

    for name in (
        ".github/workflows/20-application-images.yml",
        "CI_CD_KIT_LOCAL/workflows/20-application-images.yml",
    ):
        workflow = (ROOT / name).read_text(encoding="utf-8")
        assert "'compose.yaml'" in workflow
        assert "'infra/templates/**'" in workflow
        assert "if: ${{ always() }}" in workflow


def test_web_tmpfs_is_writable_by_the_unprivileged_nginx_user() -> None:
    expected_tmpfs = [
        "/var/cache/nginx:mode=0755,uid=10001,gid=10001",
        "/var/run:mode=0755,uid=10001,gid=10001",
    ]

    for name in ("compose.yaml", "infra/templates/compose.yaml.tmpl"):
        compose = yaml.safe_load((ROOT / name).read_text(encoding="utf-8"))
        for service in (
            "pige360-web",
            "pige360-platform-console",
            "pige360-branding-studio",
            "pige360-tenant-download-center",
        ):
            assert compose["services"][service]["tmpfs"] == expected_tmpfs


def test_release_promotes_a_versioned_pre_release_with_all_application_artifacts() -> None:
    workflow = (ROOT / ".github/workflows/50-release.yml").read_text(encoding="utf-8")
    kit_workflow = (ROOT / "CI_CD_KIT_LOCAL/workflows/50-release.yml").read_text(encoding="utf-8")

    for candidate in (workflow, kit_workflow):
        assert "push:" in candidate
        assert "branches: [main]" in candidate
        assert "- VERSION" in candidate
        assert "contents: write" in candidate
        assert "package-web-pwa.sh" in candidate
        assert "build-all.sh" in candidate
        assert "build-android.sh" in candidate
        assert "build-ios.sh" in candidate
        assert "actions/download-artifact@v4" in candidate
        assert "publish-github-release.sh release/publish" in candidate
        assert "publishable" in candidate
        assert 'gh release view "$tag"' in candidate


def test_native_and_remote_release_scripts_emit_publishable_artifacts() -> None:
    ios = (ROOT / "scripts/mobile/build-ios.sh").read_text(encoding="utf-8")
    android = (ROOT / "scripts/mobile/build-android.sh").read_text(encoding="utf-8")
    publisher = (ROOT / "scripts/release/publish-github-release.sh").read_text(encoding="utf-8")
    version_check = (ROOT / "scripts/validation/validate_version_consistency.py").read_text(encoding="utf-8")
    ci = (ROOT / "scripts/ci/run_all.py").read_text(encoding="utf-8")

    assert "*.ipa" in ios
    assert "Esperadas 5 IPAs unsigned" in ios
    assert "tauri ios init --ci" in ios
    assert "restore_ios_platform_config" in ios
    assert "CODE_SIGNING_ALLOWED=NO" in ios
    assert "Falha ao gerar o projeto iOS" in ios
    assert "tauri android init --ci --skip-targets-install" in android
    assert "NDK_HOME" in android
    assert "Falha ao gerar o projeto Android" in android
    assert "Esperados 7 APKs" in android
    assert "Esperados 7 AABs" in android
    for workflow_name in ("31-build-desktop.yml", "32-build-android.yml", "33-build-ios.yml"):
        workflow = yaml.safe_load((ROOT / ".github/workflows" / workflow_name).read_text(encoding="utf-8"))
        triggers = workflow.get("on", workflow.get(True, {}))
        assert "pull_request" in triggers
    android_workflow = (ROOT / ".github/workflows/32-build-android.yml").read_text(encoding="utf-8")
    assert "ndk_version='27.3.13750724'" in android_workflow
    assert "ANDROID_NDK_HOME" in android_workflow
    for app in ("family-app", "teacher-app", "student-app", "admin-app", "pos-app", "kiosk-app", "timeclock-app"):
        mobile_lib = (ROOT / "apps" / app / "src-tauri/src/lib.rs").read_text(encoding="utf-8")
        mobile_main = (ROOT / "apps" / app / "src-tauri/src/main.rs").read_text(encoding="utf-8")
        assert "#[cfg_attr(mobile, tauri::mobile_entry_point)]" in mobile_lib
        assert "pub fn run()" in mobile_lib
        assert "::run();" in mobile_main
    for extension in ("*.apk", "*.aab", "*.ipa", "*.dmg", "*.msi", "*.AppImage"):
        assert extension in publisher
    assert "versões publicadas são imutáveis" in publisher
    assert "version-consistency" in ci
    assert "mismatches" in version_check


def test_release_build_readiness_prevents_known_native_build_regressions() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/validation/validate_release_build_readiness.py"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
