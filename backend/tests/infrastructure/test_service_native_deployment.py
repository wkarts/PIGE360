from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[3]
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
ENVIRONMENTS = ("develop", "production")
OPS_SERVICES = {
    "pige360-secrets-init",
    "pige360-config-init",
    "pige360-data-init",
    "pige360-config-validate",
    "pige360-migrations-control",
    "pige360-migrations-tenants",
    "pige360-readiness",
    "pige360-bootstrap-admin",
    "pige360-secret-set",
    "pige360-backup",
    "pige360-restore",
    "pige360-diagnostics",
}


def _compose(environment: str) -> dict:
    return yaml.safe_load((ROOT / "deployments" / environment / "compose.yaml").read_text(encoding="utf-8"))


def test_standalone_packages_require_only_yaml_and_env() -> None:
    for environment in ENVIRONMENTS:
        directory = ROOT / "deployments" / environment
        files = {path.relative_to(directory).as_posix() for path in directory.rglob("*") if path.is_file()}
        assert files == {".env.example", "compose.yaml", "README.md", "GENERATED-MANIFEST.json", "SHA256SUMS"}
        assert not any(path.endswith(".sh") for path in files)


def test_operational_services_replace_host_scripts() -> None:
    for environment in ENVIRONMENTS:
        document = _compose(environment)
        services = document["services"]
        assert OPS_SERVICES <= set(services)
        assert "pige360-app-init" not in services
        assert services["pige360-migrations-control"]["command"] == ["migrate-control"]
        assert services["pige360-migrations-tenants"]["command"] == ["migrate-tenants"]
        assert services["pige360-migrations-tenants"]["depends_on"]["pige360-migrations-control"] == {
            "condition": "service_completed_successfully"
        }
        assert services["pige360-api"]["depends_on"]["pige360-migrations-tenants"] == {
            "condition": "service_completed_successfully"
        }


def test_operational_services_have_least_privilege() -> None:
    for environment in ENVIRONMENTS:
        document = _compose(environment)
        for name in OPS_SERVICES:
            service = document["services"][name]
            mounts = service.get("volumes", [])
            assert "/var/run/docker.sock" not in "\n".join(str(item) for item in mounts), name
            default_tag = "develop" if environment == "develop" else VERSION
            assert service["image"].endswith(f"/pige360-ops:${{PIGE360_IMAGE_TAG:-{default_tag}}}")
            assert service["read_only"] is True
            assert "no-new-privileges:true" in service["security_opt"]
        for name in OPS_SERVICES - {
            "pige360-secrets-init",
            "pige360-config-init",
            "pige360-data-init",
            "pige360-config-validate",
            "pige360-migrations-control",
            "pige360-migrations-tenants",
        }:
            assert document["services"][name]["profiles"] == ["operations"]


def test_service_native_state_is_isolated_by_compose_project() -> None:
    for environment in ENVIRONMENTS:
        document = _compose(environment)
        for definition in document["volumes"].values():
            assert "name" not in (definition or {})
        for service in document["services"].values():
            for mount in service.get("volumes", []):
                assert not str(mount).startswith("./")
