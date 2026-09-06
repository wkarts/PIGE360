from __future__ import annotations

from pathlib import Path

import yaml

from scripts.validation.validate_deployments import validate


ROOT = Path(__file__).resolve().parents[3]


FIRST_PARTY_IMAGES = (
    "pige360-api",
    "pige360-migrations",
    "pige360-worker",
    "pige360-web",
    "pige360-platform-console",
    "pige360-branding-studio",
    "pige360-tenant-download-center",
)


def _env(environment: str) -> str:
    production = environment == "production"
    values = {
        "COMPOSE_PROJECT_NAME": f"pige360-{environment}",
        "PIGE360_PROJECT_NAME": f"pige360-{environment}",
        "PIGE360_ENVIRONMENT": environment,
        "APP_ENV": "production" if production else "staging",
        "APP_VERSION": "1.1.1",
        "PIGE360_IMAGE_REGISTRY": "ghcr.io/wkarts",
        "PIGE360_IMAGE_TAG": "1.1.1" if production else "develop",
        "PIGE360_DEPLOY_TARGET": "base",
        "PIGE360_SECRETS_DIR": "./secrets",
        "PIGE360_DATA_ROOT": "./volumes",
        "PLATFORM_CONSOLE_HOST": f"console.{environment}.example.test",
        "PLATFORM_API_HOST": f"api.{environment}.example.test",
        "PLATFORM_BRANDING_HOST": f"branding.{environment}.example.test",
        "PLATFORM_DOWNLOADS_HOST": f"downloads.{environment}.example.test",
        "PIGE360_BASE_DOMAIN": f"{environment}.example.test",
        "ALLOWED_PLATFORM_HOSTS": f"console.{environment}.example.test,api.{environment}.example.test",
        "CORS_ALLOWED_ORIGINS": f"https://console.{environment}.example.test",
        "WEB_BIND_HOST": "127.0.0.1",
        "WEB_BIND_PORT": "58080" if production else "48080",
        "CONSOLE_BIND_HOST": "127.0.0.1",
        "CONSOLE_BIND_PORT": "58081" if production else "48081",
        "BRANDING_BIND_HOST": "127.0.0.1",
        "BRANDING_BIND_PORT": "58082" if production else "48082",
        "DOWNLOADS_BIND_HOST": "127.0.0.1",
        "DOWNLOADS_BIND_PORT": "58083" if production else "48083",
    }
    return "\n".join(f"{key}={value}" for key, value in values.items()) + "\n"


def _compose() -> str:
    return """name: ${COMPOSE_PROJECT_NAME}
services:
  pige360-postgres-control:
    image: postgres:17.5-bookworm
    volumes:
      - control-data:/var/lib/postgresql/data
    networks: [data]
  pige360-app-init:
    image: ${PIGE360_IMAGE_REGISTRY}/pige360-migrations:${PIGE360_IMAGE_TAG}
    pull_policy: always
    env_file: [.env]
    networks: [data]
  pige360-api:
    image: ${PIGE360_IMAGE_REGISTRY}/pige360-api:${PIGE360_IMAGE_TAG}
    pull_policy: always
    env_file: [.env]
    networks: [app, data]
  pige360-worker-default:
    image: ${PIGE360_IMAGE_REGISTRY}/pige360-worker:${PIGE360_IMAGE_TAG}
    pull_policy: always
    env_file: [.env]
    networks: [data]
  pige360-web:
    image: ${PIGE360_IMAGE_REGISTRY}/pige360-web:${PIGE360_IMAGE_TAG}
    pull_policy: always
    env_file: [.env]
    ports:
      - ${WEB_BIND_HOST}:${WEB_BIND_PORT}:8080
    networks: [app]
  pige360-platform-console:
    image: ${PIGE360_IMAGE_REGISTRY}/pige360-platform-console:${PIGE360_IMAGE_TAG}
    pull_policy: always
    env_file: [.env]
    ports:
      - ${CONSOLE_BIND_HOST}:${CONSOLE_BIND_PORT}:8080
    networks: [app]
  pige360-branding-studio:
    image: ${PIGE360_IMAGE_REGISTRY}/pige360-branding-studio:${PIGE360_IMAGE_TAG}
    pull_policy: always
    env_file: [.env]
    ports:
      - ${BRANDING_BIND_HOST}:${BRANDING_BIND_PORT}:8080
    networks: [app]
  pige360-tenant-download-center:
    image: ${PIGE360_IMAGE_REGISTRY}/pige360-tenant-download-center:${PIGE360_IMAGE_TAG}
    pull_policy: always
    env_file: [.env]
    ports:
      - ${DOWNLOADS_BIND_HOST}:${DOWNLOADS_BIND_PORT}:8080
    networks: [app]
volumes:
  control-data: {}
networks:
  app: {}
  data:
    internal: true
"""


def _write_project(root: Path) -> None:
    (root / "VERSION").write_text("1.1.1\n", encoding="utf-8")
    catalog = root / "deploy/images/catalog.yaml"
    catalog.parent.mkdir(parents=True)
    catalog.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "first_party": [
                    {"service": name.removeprefix("pige360-"), "image": f"{name}:${{PIGE360_IMAGE_TAG}}", "required": True}
                    for name in FIRST_PARTY_IMAGES
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    for environment in ("develop", "production"):
        directory = root / "deployments" / environment
        directory.mkdir(parents=True)
        (directory / ".env.example").write_text(_env(environment), encoding="utf-8")
        (directory / "compose.yaml").write_text(_compose(), encoding="utf-8")
    variants = {
        "dockge/develop/compose.yaml": "develop",
        "dockge/production/compose.yaml": "production",
        "cloudpanel/develop/compose.yaml": "develop",
        "cloudpanel/production/compose.yaml": "production",
        "portainer/develop/stack.yaml": "develop",
        "portainer/production/stack.yaml": "production",
    }
    for relative, environment in variants.items():
        target = root / "deployments" / relative
        target.parent.mkdir(parents=True)
        target.write_text(_compose(), encoding="utf-8")


def _all_errors(report: dict) -> str:
    return "\n".join(
        error
        for check in report["checks"]
        for error in check.get("errors", [])
    )


def _mutate_yaml(path: Path, mutate) -> None:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    mutate(document)
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")


def test_valid_standalone_deployment_matrix_passes(tmp_path: Path) -> None:
    _write_project(tmp_path)

    report = validate(tmp_path)

    assert report["status"] == "passed", _all_errors(report)


def test_missing_deployment_files_fail_with_exact_paths(tmp_path: Path) -> None:
    report = validate(tmp_path)

    assert report["status"] == "failed"
    assert "deployments/develop/compose.yaml" in _all_errors(report)
    assert "deployments/production/.env.example" in _all_errors(report)
    assert "deployments/portainer/production/stack.yaml" in _all_errors(report)


def test_develop_compose_must_consume_the_develop_tag(tmp_path: Path) -> None:
    _write_project(tmp_path)
    compose = tmp_path / "deployments/develop/compose.yaml"
    _mutate_yaml(
        compose,
        lambda document: document["services"]["pige360-api"].update(
            image="${PIGE360_IMAGE_REGISTRY}/pige360-api:${APP_VERSION}"
        ),
    )

    report = validate(tmp_path)

    assert report["status"] == "failed"
    assert "tag '1.1.1' difere da tag develop declarada 'develop'" in _all_errors(report)


def test_develop_compose_cannot_apply_production_environment(tmp_path: Path) -> None:
    _write_project(tmp_path)
    compose = tmp_path / "deployments/develop/compose.yaml"
    _mutate_yaml(
        compose,
        lambda document: document["services"]["pige360-api"].update(
            environment={"APP_ENV": "production"}
        ),
    )

    report = validate(tmp_path)

    assert report["status"] == "failed"
    assert "APP_ENV='production'; esperado 'staging'" in _all_errors(report)


def test_catalog_and_every_deployment_must_consume_the_same_images(tmp_path: Path) -> None:
    _write_project(tmp_path)
    compose = tmp_path / "deployments/develop/compose.yaml"
    _mutate_yaml(compose, lambda document: document["services"].pop("pige360-platform-console"))

    report = validate(tmp_path)

    assert report["status"] == "failed"
    errors = _all_errors(report)
    assert "pige360-platform-console" in errors
    assert "imagens first-party diferentes" in errors


def test_first_party_services_must_receive_the_runtime_env_file(tmp_path: Path) -> None:
    _write_project(tmp_path)
    compose = tmp_path / "deployments/develop/compose.yaml"
    _mutate_yaml(
        compose,
        lambda document: document["services"]["pige360-api"].pop("env_file"),
    )

    report = validate(tmp_path)

    assert report["status"] == "failed"
    assert "pige360-api: env_file .env obrigatorio" in _all_errors(report)


def test_first_party_images_must_always_be_pulled(tmp_path: Path) -> None:
    _write_project(tmp_path)
    compose = tmp_path / "deployments/develop/compose.yaml"
    _mutate_yaml(
        compose,
        lambda document: document["services"]["pige360-api"].update(
            pull_policy="missing"
        ),
    )

    report = validate(tmp_path)

    assert report["status"] == "failed"
    assert "pige360-api: pull_policy='always' obrigatoria" in _all_errors(report)


def test_production_rejects_moving_tags_builds_and_yaml_anchors(tmp_path: Path) -> None:
    _write_project(tmp_path)
    env = tmp_path / "deployments/production/.env.example"
    env.write_text(env.read_text(encoding="utf-8").replace("PIGE360_IMAGE_TAG=1.1.1", "PIGE360_IMAGE_TAG=develop"), encoding="utf-8")
    compose = tmp_path / "deployments/production/compose.yaml"
    compose.write_text(
        compose.read_text(encoding="utf-8").replace(
            "services:\n",
            "x-forbidden: &forbidden\n  value: true\nservices:\n",
        ).replace(
            "  pige360-api:\n",
            "  pige360-api:\n    build: ../..\n",
        ).replace(
            "image: postgres:17.5-bookworm",
            "image: postgres:latest",
        ),
        encoding="utf-8",
    )

    report = validate(tmp_path)

    errors = _all_errors(report)
    assert report["status"] == "failed"
    assert "producao exige tag SemVer estavel" in errors
    assert "anchors/aliases YAML proibidos" in errors
    assert "build e proibido" in errors
    assert "tag movel/ausente proibida em producao: postgres:latest" in errors


def test_develop_and_production_cannot_share_fixed_volume_names(tmp_path: Path) -> None:
    _write_project(tmp_path)
    for environment in ("develop", "production"):
        compose = tmp_path / f"deployments/{environment}/compose.yaml"
        _mutate_yaml(
            compose,
            lambda document: document["volumes"]["control-data"].update(
                name="pige360-control-data"
            ),
        )

    report = validate(tmp_path)

    assert report["status"] == "failed"
    assert "volumes internos compartilhados" in _all_errors(report)


def test_required_environment_keys_cannot_be_omitted(tmp_path: Path) -> None:
    _write_project(tmp_path)
    env = tmp_path / "deployments/develop/.env.example"
    env.write_text(
        "\n".join(
            line for line in env.read_text(encoding="utf-8").splitlines()
            if not line.startswith("CORS_ALLOWED_ORIGINS=")
        ) + "\n",
        encoding="utf-8",
    )

    report = validate(tmp_path)

    assert report["status"] == "failed"
    assert "chave obrigatoria ausente: CORS_ALLOWED_ORIGINS" in _all_errors(report)


def test_deployment_version_must_match_the_project_version(tmp_path: Path) -> None:
    _write_project(tmp_path)
    (tmp_path / "VERSION").write_text("1.1.0\n", encoding="utf-8")

    report = validate(tmp_path)

    assert report["status"] == "failed"
    errors = _all_errors(report)
    assert "APP_VERSION='1.1.1' difere de VERSION='1.1.0'" in errors


def test_internal_services_cannot_publish_host_ports(tmp_path: Path) -> None:
    _write_project(tmp_path)
    compose = tmp_path / "deployments/develop/compose.yaml"
    _mutate_yaml(
        compose,
        lambda document: document["services"]["pige360-postgres-control"].update(
            ports=["127.0.0.1:55432:5432"]
        ),
    )

    report = validate(tmp_path)

    assert report["status"] == "failed"
    assert "servico interno pige360-postgres-control nao pode publicar portas" in _all_errors(report)


def test_mounted_configuration_files_must_exist_in_the_package(tmp_path: Path) -> None:
    _write_project(tmp_path)
    compose = tmp_path / "deployments/develop/compose.yaml"
    _mutate_yaml(
        compose,
        lambda document: document["services"]["pige360-api"].update(
            volumes=["./config/missing.yaml:/etc/pige360/missing.yaml:ro"]
        ),
    )

    report = validate(tmp_path)

    assert report["status"] == "failed"
    assert "configuracao ausente: ./config/missing.yaml" in _all_errors(report)


def test_repository_deployments_pass_the_executable_contract() -> None:
    report = validate(ROOT)

    assert report["status"] == "passed", _all_errors(report)
