from __future__ import annotations

import json
import importlib.util
import os
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
    assert "cloudpanel:" in release
    assert "build-runtime-images.sh all" in release
    assert "cloudpanel-linux-x64" in release
    assert "cloudpanel-linux-x86" in release
    assert "scripts/mobile/build-android.sh" in release
    assert "scripts/mobile/build-ios.sh" in release


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


def test_release_coordinates_web_server_and_native_distribution() -> None:
    workflow = (ROOT / ".github/workflows/50-release.yml").read_text(encoding="utf-8")
    kit_workflow = (ROOT / "CI_CD_KIT_LOCAL/workflows/50-release.yml").read_text(encoding="utf-8")

    assert workflow == kit_workflow
    assert "push:" in workflow
    assert "branches: [main]" in workflow
    assert "contents: write" in workflow
    assert "compute-next-version.mjs" in workflow
    assert "package-web-pwa.sh" in workflow
    assert "build-runtime-images.sh all" in workflow
    assert "package-local.sh --output-dir release/output" in workflow
    assert "actions/download-artifact@v4" in workflow
    assert "collect-release-assets.mjs" in workflow
    assert "enforce-release-policy.mjs" in workflow
    assert "allow_partial_release:" in workflow
    assert "release_tag:" in workflow
    assert "prerelease_id=" in workflow
    assert "--prerelease" in workflow
    assert "--draft" in workflow
    assert 'test "$manifest_count" -eq 13' in workflow
    assert "cargo metadata --manifest-path rust/Cargo.toml --locked" in workflow
    assert "scripts/mobile/build-android.sh" in workflow
    assert "scripts/mobile/build-ios.sh" in workflow
    assert "scripts/desktop/build-all.sh" in workflow
    for target in (
        "desktop-windows-x64",
        "desktop-windows-x86",
        "desktop-linux-x64",
        "desktop-linux-arm64",
        "desktop-macos-x64",
        "desktop-macos-arm64",
        "web-pwa",
        "cloudpanel-linux-x64",
        "cloudpanel-linux-x86",
        "android-arm64-apk",
        "android-aab",
        "ios-arm64-unsigned-ipa",
    ):
        assert target in workflow


def test_native_and_release_workflows_match_the_local_ci_kit() -> None:
    canonical_names = {path.name for path in (ROOT / ".github/workflows").glob("*.yml")}
    mirrored_names = {path.name for path in (ROOT / "CI_CD_KIT_LOCAL/workflows").glob("*.yml")}

    assert canonical_names == mirrored_names
    for name in sorted(canonical_names):
        canonical = (ROOT / ".github/workflows" / name).read_bytes()
        mirrored = (ROOT / "CI_CD_KIT_LOCAL/workflows" / name).read_bytes()
        assert canonical == mirrored, name


def test_native_builds_validate_pull_requests_and_join_official_release() -> None:
    release = (ROOT / ".github/workflows/50-release.yml").read_text(encoding="utf-8")
    version_check = (ROOT / "scripts/validation/validate_version_consistency.py").read_text(encoding="utf-8")
    ci = (ROOT / "scripts/ci/run_all.py").read_text(encoding="utf-8")
    entrypoint = (ROOT / "scripts/ci/pytest_node_entry.py").read_text(encoding="utf-8")

    assert "PIGE360 PYTEST NODE FAILURE" in entrypoint
    assert "report.longreprtext" in entrypoint
    assert "version-consistency" in ci
    assert "mismatches" in version_check

    for workflow_name in ("31-build-desktop.yml", "32-build-android.yml", "33-build-ios.yml"):
        workflow = yaml.safe_load((ROOT / ".github/workflows" / workflow_name).read_text(encoding="utf-8"))
        workflow_triggers = workflow.get("on", workflow.get(True, {})) or {}
        assert "workflow_dispatch" in workflow_triggers
        assert "pull_request" in workflow_triggers
        assert "push" not in workflow_triggers

    android_workflow = (ROOT / ".github/workflows/32-build-android.yml").read_text(encoding="utf-8")
    assert "inputs.sign && inputs.scope != 'all'" in android_workflow
    ios_workflow = (ROOT / ".github/workflows/33-build-ios.yml").read_text(encoding="utf-8")
    assert "build_mode=local-signing" in ios_workflow
    assert "requested_mode=store" in ios_workflow
    assert "scripts/mobile/sign-ios.sh" in ios_workflow
    tenant_workflow = (ROOT / ".github/workflows/34-build-tenant-apps.yml").read_text(encoding="utf-8")
    assert "if: ${{ inputs.publish_stores == true }}" in tenant_workflow
    assert "REMOTE_RELEASE_ENABLED" in tenant_workflow
    assert "exit 78" in tenant_workflow

    for required in (
        "scripts/mobile/build-android.sh",
        "scripts/mobile/build-ios.sh",
        "scripts/desktop/build-all.sh",
        "write-build-status.mjs",
        "collect-release-assets.mjs",
    ):
        assert required in release

    collector = (ROOT / "scripts/release/collect-release-assets.mjs").read_text(encoding="utf-8")
    for extension in (".apk", ".aab", ".ipa", ".dmg", ".msi", ".exe", ".AppImage", ".deb", ".rpm"):
        assert extension in collector
    assert "Cargo target não pode ser publicado" in collector
    for script_name in (
        "scripts/desktop/build-all.sh",
        "scripts/mobile/build-ios.sh",
        "scripts/mobile/build-tenant-app.sh",
        "scripts/mobile/sign-ios.sh",
    ):
        script = (ROOT / script_name).read_text(encoding="utf-8")
        assert "shasum -a 256" in script
        assert "sha256sum" in script


def test_web_pwa_packager_accepts_stable_and_prerelease_semver(tmp_path: Path) -> None:
    script = ROOT / "scripts/release/package-web-pwa.sh"
    script_text = script.read_text(encoding="utf-8")
    assert "scripts/validation/validate_pwa_builds.py" in script_text
    assert 'unzip -tq "$archive"' in script_text
    for version in ("1.0.1", "1.1.0", "1.0.1-alpha.2", "2.3.4-rc.1+build.9"):
        (tmp_path / "VERSION").write_text(version + "\n", encoding="utf-8")
        result = subprocess.run(
            ["bash", str(script), "--validate-version-only"],
            cwd=tmp_path,
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr

    for version in ("01.0.0", "1.0", "1.0.0-01", "1.0.0-"):
        (tmp_path / "VERSION").write_text(version + "\n", encoding="utf-8")
        result = subprocess.run(
            ["bash", str(script), "--validate-version-only"],
            cwd=tmp_path,
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0


def test_version_validator_defaults_to_stable_and_requires_explicit_prerelease() -> None:
    path = ROOT / "scripts/validation/validate_version_consistency.py"
    spec = importlib.util.spec_from_file_location("pige360_version_consistency_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.is_valid_version("1.1.0") is True
    assert module.is_valid_version("1.1.0-rc.1") is False
    assert module.is_valid_version("1.1.0-rc.1", allow_prerelease=True) is True
    assert module.is_valid_version("1.1.0+build.9", allow_prerelease=True) is True
    assert module.is_valid_version("1.1.0-01", allow_prerelease=True) is False
    release = (ROOT / ".github/workflows/50-release.yml").read_text(encoding="utf-8")
    ci = (ROOT / "scripts/ci/run_all.py").read_text(encoding="utf-8")
    assert "--allow-prerelease" in release
    assert "version_command.append('--allow-prerelease')" in ci


def test_release_collector_requires_the_exact_asset_type_and_count(tmp_path: Path) -> None:
    collector = ROOT / "scripts/release/collect-release-assets.mjs"

    wrong_input = tmp_path / "wrong-input"
    wrong_artifact = wrong_input / "release-android-arm64-apk"
    wrong_artifact.mkdir(parents=True)
    (wrong_artifact / "not-an-apk.zip").write_bytes(b"zip")
    wrong_output = tmp_path / "wrong-output"
    rejected = subprocess.run(
        ["node", str(collector), "--input", str(wrong_input), "--output", str(wrong_output), "--product", "PIGE360", "--version", "1.1.0"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert rejected.returncode != 0
    assert "Tipo de artefato inesperado" in rejected.stderr

    unknown_input = tmp_path / "unknown-input"
    unknown_artifact = unknown_input / "release-untracked"
    unknown_artifact.mkdir(parents=True)
    (unknown_artifact / "payload.zip").write_bytes(b"zip")
    unknown_output = tmp_path / "unknown-output"
    rejected_unknown = subprocess.run(
        ["node", str(collector), "--input", str(unknown_input), "--output", str(unknown_output), "--product", "PIGE360", "--version", "1.1.0"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert rejected_unknown.returncode != 0
    assert "Contexto de artefato desconhecido" in rejected_unknown.stderr

    input_dir = tmp_path / "count-input"
    artifact_dir = input_dir / "release-android-arm64-apk"
    status_dir = input_dir / "release-status-android-arm64-apk"
    core_dir = input_dir / "release-core-web-server"
    artifact_dir.mkdir(parents=True)
    status_dir.mkdir(parents=True)
    core_dir.mkdir(parents=True)
    (core_dir / ".pige360-delivery-root.json").write_text("{}", encoding="utf-8")
    for index in range(6):
        (artifact_dir / f"app-{index}.apk").write_bytes(f"apk-{index}".encode())
    status = {
        "schemaVersion": 1,
        "id": "android-arm64-apk",
        "label": "Android APK ARM64",
        "platform": "android",
        "arch": "arm64",
        "target": "aarch64-linux-android",
        "artifact": "release-android-arm64-apk",
        "status": "success",
        "success": True,
        "runUrl": None,
        "error": None,
    }
    (status_dir / "android-arm64-apk.status.json").write_text(json.dumps(status), encoding="utf-8")
    output_dir = tmp_path / "count-output"
    result = subprocess.run(
        ["node", str(collector), "--input", str(input_dir), "--output", str(output_dir), "--product", "PIGE360", "--version", "1.1.0"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    release_status = json.loads((output_dir / "RELEASE-STATUS.json").read_text(encoding="utf-8"))
    release_manifest = json.loads((output_dir / "RELEASE-MANIFEST.json").read_text(encoding="utf-8"))
    android = next(target for target in release_status["targets"] if target["id"] == "android-arm64-apk")
    assert android["success"] is False
    assert android["assetCounts"] == {".apk": 6}
    assert "exatamente 7 .apk" in android["error"]
    assert all(".pige360-delivery-root.json" not in asset["source"] for asset in release_manifest["assets"])


def test_release_recovery_rebuilds_full_matrix_without_reusing_assets() -> None:
    recovery = (ROOT / ".github/workflows/51-recover-release.yml").read_text(encoding="utf-8")

    assert "release_tag:" in recovery
    assert "source_run_id:" in recovery
    assert "allow_partial_release:" in recovery
    assert "prerelease_id=" in recovery
    assert 'GITHUB_REF" = \'refs/heads/main\'' in recovery
    assert "rust/Cargo.lock" in recovery
    assert "manifest_count" in recovery
    assert '"$manifest_count" -eq 13' in recovery
    assert "gh workflow run 50-release.yml" in recovery
    assert "reconstruirá os 16 alvos a partir da tag exata" in recovery
    assert "Nenhum artefato de execução anterior foi publicado ou reaproveitado" in recovery
    for forbidden in (
        "actions/download-artifact",
        "publish-github-release.sh",
        "gh release create",
        "gh release upload",
    ):
        assert forbidden not in recovery


def test_canonical_multitenant_deploy_contract_is_present() -> None:
    domain = yaml.safe_load((ROOT / "deploy/domains/domain-contract.yaml").read_text(encoding="utf-8"))
    images = yaml.safe_load((ROOT / "deploy/images/catalog.yaml").read_text(encoding="utf-8"))
    provisioning = yaml.safe_load((ROOT / "deploy/provisioning/tenant-contract.yaml").read_text(encoding="utf-8"))
    edge = (ROOT / "deploy/compose/compose.edge.yaml").read_text(encoding="utf-8")
    logging_compose = yaml.safe_load((ROOT / "deploy/compose/compose.logging.yaml").read_text(encoding="utf-8"))
    otel = (ROOT / "infra/monitoring/otel-collector.yaml").read_text(encoding="utf-8")
    connect_api = yaml.safe_load((ROOT / "infra/connect-api/integration.yaml").read_text(encoding="utf-8"))

    assert domain["base_domain"] == "pige360.com.br"
    assert domain["tenant"]["wildcard"] == "*.pige360.com.br"
    assert domain["tenant"]["dns_per_tenant_required"] is False
    assert {"api", "console", "ops", "www", "admin", "platform"} <= set(domain["reserved_slugs"])
    assert any(item["service"] == "web" and item["app"] == "apps/tenant-admin-web" for item in images["first_party"])
    assert any(step["id"] == "canonical_domain" for step in provisioning["steps"])
    assert "HostRegexp(`^[a-z0-9-]+\\.${TENANT_DEFAULT_BASE_DOMAIN:-pige360.com.br}$`)" in edge
    assert "dnschallenge.provider=cloudflare" in edge
    assert "PIGE360_TRAEFIK_DYNAMIC_DIR_INTERNAL" in edge
    assert "pige360-traefik-dynamic" in edge
    assert "pige360-edge-init" in edge
    assert "pige360-alloy" in logging_compose["services"]
    assert "otlphttp/loki" in otel
    assert connect_api["provider"] == "connect_api"
    assert connect_api["compatibility"]["meta"] is True
    assert not (ROOT / "infra/evolution/integration.yaml").exists()


def test_release_publisher_preserves_colliding_assets_and_deduplicates_identical_files(tmp_path: Path) -> None:
    assets = tmp_path / "assets"
    (assets / "one").mkdir(parents=True)
    (assets / "two").mkdir()
    (assets / "three").mkdir()
    (assets / "one" / "build-report.json").write_text('{"source":"one"}', encoding="utf-8")
    (assets / "two" / "build-report.json").write_text('{"source":"two"}', encoding="utf-8")
    (assets / "three" / "build-report.json").write_text('{"source":"one"}', encoding="utf-8")
    (tmp_path / "VERSION").write_text("1.0.1\n", encoding="utf-8")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh_log = tmp_path / "gh.log"
    gh = bin_dir / "gh"
    gh.write_text(
        "#!/usr/bin/env bash\n"
        "set -eu\n"
        "printf '%s\\n' \"$*\" >> \"$GH_LOG\"\n"
        "if [ \"$1\" = release ] && [ \"$2\" = view ]; then exit 1; fi\n"
        "if [ \"$1\" = release ] && [ \"$2\" = create ]; then exit 0; fi\n"
        "exit 1\n",
        encoding="utf-8",
    )
    gh.chmod(0o755)

    result = subprocess.run(
        ["bash", str(ROOT / "scripts/release/publish-github-release.sh"), str(assets)],
        cwd=tmp_path,
        env={
            **os.environ,
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "GH_LOG": str(gh_log),
            "GITHUB_TOKEN": "test-token",
            "GITHUB_SHA": "c60d0dce44f3db25d46c1e62e4fc3f0432a55d77",
            "REMOTE_RELEASE_ENABLED": "true",
        },
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    stage = assets / ".github-release-assets"
    assert sorted(item.name for item in stage.iterdir()) == [
        "build-report.json",
        "two--build-report.json",
    ]
    assert (stage / "build-report.json").read_text(encoding="utf-8") == '{"source":"one"}'
    assert (stage / "two--build-report.json").read_text(encoding="utf-8") == '{"source":"two"}'
    assert "Artefato idêntico deduplicado: build-report.json" in result.stdout
    assert "Artefato com nome repetido preservado como: two--build-report.json" in result.stdout
    assert "release create v1.0.1" in gh_log.read_text(encoding="utf-8")


def test_release_build_readiness_matches_web_server_release_contract() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/validation/validate_release_build_readiness.py"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
