from __future__ import annotations

from pathlib import Path


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
    assert "compose_smoke.outcome == 'success'" in release


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
