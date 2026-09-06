from __future__ import annotations

import ast
import hashlib
import json
import os
import subprocess
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[3]
EXPECTED_IMAGES = {
    "pige360-base-python",
    "pige360-base-node",
    "pige360-base-runtime",
    "pige360-base-rust-tauri",
    "pige360-api",
    "pige360-web",
    "pige360-platform-console",
    "pige360-branding-studio",
    "pige360-tenant-download-center",
    "pige360-worker",
    "pige360-migrations",
    "pige360-ops",
    "pige360-reporting",
}
DEPLOY_IMAGES = {
    "pige360-api",
    "pige360-web",
    "pige360-platform-console",
    "pige360-branding-studio",
    "pige360-tenant-download-center",
    "pige360-worker",
    "pige360-ops",
}


def _bash_array(name: str) -> list[str]:
    result = subprocess.run(
        [
            "bash",
            "-c",
            f'. scripts/oci/image-catalog.sh; printf "%s\\n" "${{{name}[@]}}"',
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.splitlines()


def _fake_docker(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True)
    state = tmp_path / "registry-state.txt"
    log = tmp_path / "docker.log"
    state.write_text("", encoding="utf-8")
    docker = bin_dir / "docker"
    docker.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "printf '%s\\n' \"$*\" >> \"$FAKE_DOCKER_LOG\"\n"
        "if [[ \"${1:-} ${2:-}\" == 'image inspect' ]]; then\n"
        "  if [[ \" $* \" == *' --format '* ]]; then printf '%s\\n' 'sha256:fixture'; fi\n"
        "  exit 0\n"
        "fi\n"
        "if [[ \"${1:-}\" == tag ]]; then exit 0; fi\n"
        "if [[ \"${1:-}\" == push ]]; then printf '%s\\n' \"$2\" >> \"$FAKE_DOCKER_STATE\"; exit 0; fi\n"
        "if [[ \"${1:-} ${2:-} ${3:-}\" == 'buildx imagetools create' ]]; then\n"
        "  destination=''\n"
        "  source_ref=\"${@: -1}\"\n"
        "  while [[ $# -gt 0 ]]; do\n"
        "    if [[ \"$1\" == --tag ]]; then destination=\"$2\"; break; fi\n"
        "    shift\n"
        "  done\n"
        "  grep -Fqx -- \"$source_ref\" \"$FAKE_DOCKER_STATE\" || exit 1\n"
        "  printf '%s\\n' \"$destination\" >> \"$FAKE_DOCKER_STATE\"\n"
        "  exit 0\n"
        "fi\n"
        "if [[ \"${1:-} ${2:-} ${3:-}\" == 'buildx imagetools inspect' ]]; then\n"
        "  ref=\"$4\"\n"
        "  grep -Fqx -- \"$ref\" \"$FAKE_DOCKER_STATE\" || exit 1\n"
        "  if [[ -n \"${FAKE_DOCKER_DIVERGENT_REF:-}\" && \"$ref\" == \"$FAKE_DOCKER_DIVERGENT_REF\" ]]; then\n"
        "    printf '%s\\n' '{\"schemaVersion\":2,\"divergent\":true}'\n"
        "  else\n"
        "    printf '%s\\n' '{\"schemaVersion\":2,\"config\":{\"digest\":\"sha256:fixture\"}}'\n"
        "  fi\n"
        "  exit 0\n"
        "fi\n"
        "echo \"Comando docker falso inesperado: $*\" >&2\n"
        "exit 99\n",
        encoding="utf-8",
    )
    docker.chmod(0o755)
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}:{env['PATH']}",
            "FAKE_DOCKER_LOG": str(log),
            "FAKE_DOCKER_STATE": str(state),
            "GITHUB_REPOSITORY_OWNER": "WKARTS",
            "PIGE360_PUBLISH_SHA": "0123456789abcdef0123456789abcdef01234567",
        }
    )
    return log, env


def _fake_registry_runtime(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    bin_dir = tmp_path / "runtime-bin"
    bin_dir.mkdir(parents=True)
    log = tmp_path / "runtime-docker.log"
    docker = bin_dir / "docker"
    docker.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "printf '%s\\n' \"$*\" >> \"$FAKE_RUNTIME_DOCKER_LOG\"\n"
        "joined=\" $* \"\n"
        "if [[ \"$joined\" == *' compose version '* ]]; then printf '%s\\n' 'Docker Compose version v2.39.0'; exit 0; fi\n"
        "if [[ \"$joined\" == *' config --images '* ]]; then\n"
        "  env_file=''\n"
        "  while [[ $# -gt 0 ]]; do\n"
        "    if [[ \"$1\" == --env-file ]]; then env_file=\"$2\"; shift 2; continue; fi\n"
        "    shift\n"
        "  done\n"
        "  registry=\"$(awk -F= '$1 == \"PIGE360_IMAGE_REGISTRY\" {print $2; exit}' \"$env_file\")\"\n"
        "  tag=\"$(awk -F= '$1 == \"PIGE360_IMAGE_TAG\" {print $2; exit}' \"$env_file\")\"\n"
        "  for image in pige360-api pige360-ops pige360-worker pige360-web pige360-platform-console pige360-branding-studio pige360-tenant-download-center; do\n"
        "    printf '%s/%s:%s\\n' \"$registry\" \"$image\" \"$tag\"\n"
        "  done\n"
        "  exit 0\n"
        "fi\n"
        "if [[ \"$joined\" == *' config -q '* ]]; then exit 0; fi\n"
        "if [[ \"$joined\" == *' ps --status running --services '* ]]; then\n"
        "  printf '%s\\n' pige360-gateway pige360-api pige360-web pige360-platform-console pige360-branding-studio pige360-tenant-download-center\n"
        "  exit 0\n"
        "fi\n"
        "if [[ \"$joined\" == *' pull '* || \"$joined\" == *' up '* || \"$joined\" == *' ps --all '* || \"$joined\" == *' logs '* || \"$joined\" == *' down '* ]]; then exit 0; fi\n"
        "echo \"Comando compose falso inesperado: $*\" >&2\n"
        "exit 99\n",
        encoding="utf-8",
    )
    docker.chmod(0o755)
    curl = bin_dir / "curl"
    curl.write_text("#!/usr/bin/env sh\nprintf '%s\\n' '<html>registry smoke ok</html>'\n", encoding="utf-8")
    curl.chmod(0o755)
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}:{env['PATH']}",
            "FAKE_RUNTIME_DOCKER_LOG": str(log),
            "GITHUB_REPOSITORY_OWNER": "WKARTS",
        }
    )
    return log, env


def test_canonical_image_catalog_covers_every_deploy_image() -> None:
    assert set(_bash_array("PIGE360_ALL_IMAGE_NAMES")) == EXPECTED_IMAGES
    assert set(_bash_array("PIGE360_DEPLOY_IMAGE_NAMES")) == DEPLOY_IMAGES

    catalog = yaml.safe_load((ROOT / "deploy/images/catalog.yaml").read_text(encoding="utf-8"))
    catalog_images = {item["image"].split(":", 1)[0] for item in catalog["first_party"]}
    assert DEPLOY_IMAGES <= catalog_images
    app_factory = next(item for item in catalog["first_party"] if item["service"] == "app-factory")
    assert app_factory["image_alias_of"] == "api"
    assert app_factory["image"].startswith("pige360-api:")

    structural_tree = ast.parse((ROOT / "scripts/oci/build_structural_oci.py").read_text(encoding="utf-8"))
    structural_images: set[str] | None = None
    for node in ast.walk(structural_tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "IMAGES" for target in node.targets
        ):
            structural_images = set(ast.literal_eval(node.value))
            break
    assert structural_images == EXPECTED_IMAGES


def test_runtime_builder_builds_all_administrative_frontends() -> None:
    script = (ROOT / "scripts/oci/build-runtime-images.sh").read_text(encoding="utf-8")
    expected = {
        "pige360-web": "apps/tenant-admin-web",
        "pige360-platform-console": "apps/platform-console",
        "pige360-branding-studio": "apps/branding-studio",
        "pige360-tenant-download-center": "apps/tenant-download-center",
    }
    for image, app_dir in expected.items():
        assert f'build_image "{image}" "infra/docker/Dockerfile.web"' in script
        assert f'--build-arg "IMAGE_NAME={image}"' in script
        assert f'--build-arg "APP_DIR={app_dir}"' in script


def test_develop_publication_is_immutable_first_and_records_digests(tmp_path: Path) -> None:
    log, env = _fake_docker(tmp_path)
    output = tmp_path / "develop"
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    env["PIGE360_IMAGE_TAG"] = version
    subprocess.run(
        ["bash", "scripts/oci/publish-develop-images.sh", str(output)],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    manifest = json.loads((output / "ghcr-develop-manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 2
    assert manifest["publication_strategy"] == "two-phase-immutable-first"
    assert manifest["cross_image_atomicity"] is False
    assert manifest["registry"] == "ghcr.io/wkarts"
    assert {item["name"] for item in manifest["images"]} == EXPECTED_IMAGES
    assert all(item["digest"].startswith("sha256:") for item in manifest["images"])
    assert all(item["digest_ref"].endswith(item["digest"]) for item in manifest["images"])

    pushes = [
        line.removeprefix("push ")
        for line in log.read_text(encoding="utf-8").splitlines()
        if line.startswith("push ")
    ]
    assert len(pushes) == len(EXPECTED_IMAGES)
    assert all(ref.endswith(":develop-0123456789ab") for ref in pushes)
    creates = [
        line
        for line in log.read_text(encoding="utf-8").splitlines()
        if line.startswith("buildx imagetools create ")
    ]
    assert len(creates) == len(EXPECTED_IMAGES)
    assert all("--tag ghcr.io/wkarts/" in line and ":develop " in line for line in creates)


def test_release_publication_is_semver_and_refuses_divergent_remote_tag(tmp_path: Path) -> None:
    log, env = _fake_docker(tmp_path)
    output = tmp_path / "release"
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    env.update({"PIGE360_IMAGE_TAG": version, "PIGE360_RELEASE_VERSION": version})
    subprocess.run(
        ["bash", "scripts/oci/publish-release-images.sh", str(output)],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    manifest = json.loads((output / "ghcr-release-manifest.json").read_text(encoding="utf-8"))
    assert manifest["release_version"] == version
    assert manifest["channel_tags"] == [version, f"v{version}"]
    assert len(manifest["images"]) == len(EXPECTED_IMAGES)
    assert all(len(item["channel_refs"]) == 2 for item in manifest["images"])

    pushes = [line for line in log.read_text(encoding="utf-8").splitlines() if line.startswith("push ")]
    assert len(pushes) == len(EXPECTED_IMAGES)
    creates = [
        line for line in log.read_text(encoding="utf-8").splitlines()
        if line.startswith("buildx imagetools create ")
    ]
    assert len(creates) == len(EXPECTED_IMAGES) * 2

    divergent_log, divergent_env = _fake_docker(tmp_path / "divergent")
    divergent_ref = f"ghcr.io/wkarts/pige360-api:{version}"
    Path(divergent_env["FAKE_DOCKER_STATE"]).write_text(divergent_ref + "\n", encoding="utf-8")
    divergent_env.update(
        {
            "PIGE360_IMAGE_TAG": version,
            "PIGE360_RELEASE_VERSION": version,
            "FAKE_DOCKER_DIVERGENT_REF": divergent_ref,
        }
    )
    result = subprocess.run(
        ["bash", "scripts/oci/publish-release-images.sh", str(tmp_path / "divergent-output")],
        cwd=ROOT,
        env=divergent_env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 12
    assert "Tag SemVer remota divergente recusada" in result.stderr
    semver_promotions = [
        line for line in divergent_log.read_text(encoding="utf-8").splitlines()
        if line.startswith("buildx imagetools create ")
    ]
    assert semver_promotions == []


def test_image_workflows_publish_develop_and_release_and_match_local_kit() -> None:
    develop = (ROOT / ".github/workflows/20-application-images.yml").read_text(encoding="utf-8")
    release = (ROOT / ".github/workflows/50-release.yml").read_text(encoding="utf-8")

    assert develop == (ROOT / "CI_CD_KIT_LOCAL/workflows/20-application-images.yml").read_text(encoding="utf-8")
    assert release == (ROOT / "CI_CD_KIT_LOCAL/workflows/50-release.yml").read_text(encoding="utf-8")
    assert "publish-develop-images.sh" in develop
    assert "ghcr-develop-manifest.json" in develop
    assert "smoke-published-images.sh" in develop
    assert 'develop "$immutable_tag"' in develop
    assert "publish-release-images.sh" in release
    assert "ghcr-release-manifest.json" in release
    assert "smoke-published-images.sh" in release
    assert "production '${{ needs.plan_version.outputs.version }}'" in release
    assert "packages: write" in release
    assert "release-container-images" in release
    assert develop.count("-eq 13") >= 1
    assert release.count("-eq 13") >= 2


def test_registry_smoke_pins_remote_images_and_always_tears_down() -> None:
    script = (ROOT / "scripts/oci/smoke-published-images.sh").read_text(encoding="utf-8")
    assert "PIGE360_IMAGE_TAG" in script
    assert 'config --images' in script
    assert 'pull > "$artifact_dir/compose-pull.log"' in script
    assert "--pull never --wait" in script
    assert "/api/v1/health/ready" in script
    for frontend in (
        "pige360-web",
        "pige360-platform-console",
        "pige360-branding-studio",
        "pige360-tenant-download-center",
    ):
        assert frontend in script
    assert "down --volumes --remove-orphans" in script
    assert "trap cleanup EXIT" in script


def test_registry_smoke_contract_executes_pull_health_and_teardown(tmp_path: Path) -> None:
    log, env = _fake_registry_runtime(tmp_path)
    artifact_dir = tmp_path / "registry-smoke"
    result = subprocess.run(
        [
            "bash",
            "scripts/oci/smoke-published-images.sh",
            "develop",
            "develop-0123456789ab",
            str(artifact_dir),
        ],
        cwd=ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    manifest = json.loads((artifact_dir / "registry-smoke-manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "passed"
    assert manifest["image_tag"] == "develop-0123456789ab"
    assert manifest["teardown"] == "passed"
    docker_commands = log.read_text(encoding="utf-8")
    assert " pull" in docker_commands
    assert " up -d --no-build --pull never --wait" in docker_commands
    assert " down --volumes --remove-orphans" in docker_commands


def test_manifest_digest_fixture_is_stable() -> None:
    raw = b'{"schemaVersion":2,"config":{"digest":"sha256:fixture"}}\n'
    assert hashlib.sha256(raw).hexdigest() == "e85ed773e2882a893aeaf0e889bddf4a052d486f7e0dddd6c6f11e9edbefb337"
