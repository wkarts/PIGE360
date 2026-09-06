#!/usr/bin/env python3
"""Valida os deployments standalone de homologacao e producao do PIGE360.

O validador e deliberadamente independente do Docker. Ele fecha os erros que
`yaml.safe_load` nao detecta: ambiente errado, imagem sem registry, tag movel em
producao, volumes compartilhados entre ambientes e arquivos de configuracao
inexistentes. O smoke com Docker continua sendo uma camada adicional da CI.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

import yaml
from yaml.tokens import AliasToken, AnchorToken


REQUIRED_ENV_KEYS = {
    "COMPOSE_PROJECT_NAME",
    "PIGE360_PROJECT_NAME",
    "PIGE360_ENVIRONMENT",
    "APP_ENV",
    "APP_VERSION",
    "PIGE360_IMAGE_REGISTRY",
    "PIGE360_IMAGE_TAG",
    "PIGE360_DEPLOY_TARGET",
    "PLATFORM_CONSOLE_HOST",
    "PLATFORM_API_HOST",
    "PLATFORM_BRANDING_HOST",
    "PLATFORM_DOWNLOADS_HOST",
    "PIGE360_BASE_DOMAIN",
    "ALLOWED_PLATFORM_HOSTS",
    "CORS_ALLOWED_ORIGINS",
    "WEB_BIND_HOST",
    "BRANDING_BIND_HOST",
    "DOWNLOADS_BIND_HOST",
}

REQUIRED_ENV_ALIASES = {
    "web bind port": ("WEB_BIND_PORT", "WEB_PUBLISHED_PORT"),
    "console bind host": ("CONSOLE_BIND_HOST", "CONTROL_WEB_BIND_HOST"),
    "console bind port": ("CONSOLE_BIND_PORT", "CONTROL_WEB_PUBLISHED_PORT"),
    "branding bind port": ("BRANDING_BIND_PORT", "BRANDING_PUBLISHED_PORT"),
    "downloads bind port": ("DOWNLOADS_BIND_PORT", "DOWNLOADS_PUBLISHED_PORT"),
}

ENVIRONMENT_FILES = {
    "develop": (
        Path("deployments/develop/compose.yaml"),
        Path("deployments/develop/.env.example"),
    ),
    "production": (
        Path("deployments/production/compose.yaml"),
        Path("deployments/production/.env.example"),
    ),
}

VARIANT_FILES = {
    "dockge-develop": ("develop", Path("deployments/dockge/develop/compose.yaml")),
    "dockge-production": ("production", Path("deployments/dockge/production/compose.yaml")),
    "cloudpanel-develop": ("develop", Path("deployments/cloudpanel/develop/compose.yaml")),
    "cloudpanel-production": ("production", Path("deployments/cloudpanel/production/compose.yaml")),
    "portainer-develop": ("develop", Path("deployments/portainer/develop/stack.yaml")),
    "portainer-production": ("production", Path("deployments/portainer/production/stack.yaml")),
}

EXPECTED_ENVIRONMENT = {
    "develop": {
        "COMPOSE_PROJECT_NAME": "pige360-develop",
        "PIGE360_PROJECT_NAME": "pige360-develop",
        "PIGE360_ENVIRONMENT": "develop",
        "APP_ENV": "staging",
    },
    "production": {
        "COMPOSE_PROJECT_NAME": "pige360-production",
        "PIGE360_PROJECT_NAME": "pige360-production",
        "PIGE360_ENVIRONMENT": "production",
        "APP_ENV": "production",
    },
}

STABLE_SEMVER_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:\+[0-9A-Za-z.-]+)?$")
DEVELOP_TAG_RE = re.compile(r"^develop(?:-[0-9a-f]{7,64})?$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
ENV_KEY_RE = re.compile(r"^[A-Z_][A-Z0-9_]*$")
MOVING_PRODUCTION_TAGS = {"latest", "develop", "main", "master", "edge", "nightly", "canary", "stable"}

INTERNAL_SERVICE_RE = re.compile(
    r"postgres|redis|rabbitmq|minio|otel|prometheus|loki|alloy|worker|beat|app-init|migrations"
)
LOOPBACK_PUBLISHABLE_RE = re.compile(
    r"(?:^|-)api$|(?:^|-)web$|platform-console|branding-studio|tenant-download-center|grafana|gateway"
)
EDGE_SERVICE_RE = re.compile(r"edge|traefik")


class DeploymentValidationError(ValueError):
    """Erro legivel encontrado durante a validacao de um artefato."""


def _add(checks: list[dict[str, Any]], name: str, errors: Iterable[str], details: Any = None) -> None:
    failures = list(errors)
    checks.append(
        {
            "name": name,
            "status": "failed" if failures else "passed",
            "errors": failures,
            "details": details,
        }
    )


def load_env(path: Path) -> tuple[dict[str, str], list[str]]:
    values: dict[str, str] = {}
    errors: list[str] = []
    if not path.is_file():
        return values, [f"arquivo ausente: {path}"]

    for number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            errors.append(f"{path}:{number}: use KEY=value, sem 'export'")
            line = line[7:].lstrip()
        if "=" not in line:
            errors.append(f"{path}:{number}: linha de ambiente invalida")
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not ENV_KEY_RE.fullmatch(key):
            errors.append(f"{path}:{number}: chave invalida: {key!r}")
            continue
        if key in values:
            errors.append(f"{path}:{number}: chave duplicada: {key}")
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values, errors


def _expand_expression(expression: str, env: dict[str, str]) -> str:
    match = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)(?:(:?[-+?])(.*))?", expression, re.S)
    if not match:
        raise DeploymentValidationError(f"interpolacao invalida: ${{{expression}}}")
    key, operator, operand = match.groups()
    present = key in env
    value = env.get(key, "")
    nonempty = present and value != ""
    if not operator:
        return value
    operand = operand or ""
    if operator == ":-":
        return value if nonempty else operand
    if operator == "-":
        return value if present else operand
    if operator == ":+":
        return operand if nonempty else ""
    if operator == "+":
        return operand if present else ""
    if operator == ":?":
        if nonempty:
            return value
        raise DeploymentValidationError(operand or f"{key} e obrigatorio")
    if operator == "?":
        if present:
            return value
        raise DeploymentValidationError(operand or f"{key} e obrigatorio")
    raise DeploymentValidationError(f"operador de interpolacao invalido: {operator}")


def interpolate(value: str, env: dict[str, str]) -> str:
    """Resolve as expressoes Compose usadas nos manifests, inclusive aninhadas."""

    marker = "\0PIGE360_DOLLAR\0"
    result = value.replace("$$", marker)
    inner = re.compile(r"\$\{([^{}]+)\}")
    for _ in range(32):
        match = inner.search(result)
        if not match:
            break
        replacement = _expand_expression(match.group(1), env)
        result = result[: match.start()] + replacement + result[match.end() :]
    if "${" in result:
        raise DeploymentValidationError(f"interpolacao nao resolvida: {value}")
    return result.replace(marker, "$")


def _yaml_document(path: Path) -> tuple[dict[str, Any], str, list[str]]:
    if not path.is_file():
        return {}, "", [f"arquivo ausente: {path}"]
    text = path.read_text(encoding="utf-8")
    errors: list[str] = []
    try:
        tokens = list(yaml.scan(text))
        anchors = [token for token in tokens if isinstance(token, (AnchorToken, AliasToken))]
        if anchors:
            errors.append(f"anchors/aliases YAML proibidos: {len(anchors)} ocorrencia(s)")
    except yaml.YAMLError as exc:
        return {}, text, [f"YAML invalido: {exc}"]
    try:
        document = yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        return {}, text, [f"YAML invalido: {exc}"]
    if not isinstance(document, dict):
        errors.append("o documento Compose deve ser um objeto")
        return {}, text, errors
    services = document.get("services")
    if not isinstance(services, dict) or not services:
        errors.append("services ausente ou vazio")
    return document, text, errors


def _normal_image_name(reference: str) -> str:
    without_digest = reference.split("@", 1)[0]
    last = without_digest.rsplit("/", 1)[-1]
    return last.rsplit(":", 1)[0]


def _image_tag(reference: str) -> tuple[str | None, str | None]:
    if "@" in reference:
        return None, reference.split("@", 1)[1]
    last = reference.rsplit("/", 1)[-1]
    if ":" not in last:
        return None, None
    return last.rsplit(":", 1)[1], None


def _catalog_images(root: Path) -> tuple[set[str], set[str], list[str]]:
    path = root / "deploy/images/catalog.yaml"
    if not path.is_file():
        return set(), set(), [f"arquivo ausente: {path.relative_to(root)}"]
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        return set(), set(), [f"catalogo de imagens invalido: {exc}"]
    records = document.get("first_party")
    if not isinstance(records, list):
        return set(), set(), ["deploy/images/catalog.yaml: first_party deve ser lista"]
    available: set[str] = set()
    required: set[str] = set()
    errors: list[str] = []
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            errors.append(f"first_party[{index}] nao e objeto")
            continue
        service = str(record.get("service", "")).strip()
        image = str(record.get("image", "")).strip()
        if image == "local-build":
            name = f"pige360-{service}" if service else ""
        else:
            try:
                rendered = interpolate(image, {"PIGE360_IMAGE_TAG": "0.0.0"})
            except DeploymentValidationError:
                rendered = image
            name = _normal_image_name(rendered)
        if not name.startswith("pige360-"):
            errors.append(f"first_party[{index}] sem imagem PIGE360 valida: {image!r}")
            continue
        available.add(name)
        if record.get("required") is True or record.get("deployment_required") is True:
            required.add(name)
    return available, required, errors


def _env_file_entries(service: dict[str, Any]) -> list[str]:
    value = service.get("env_file")
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        entries: list[str] = []
        for item in value:
            if isinstance(item, str):
                entries.append(item)
            elif isinstance(item, dict) and isinstance(item.get("path"), str):
                entries.append(item["path"])
        return entries
    return []


def _service_environment(service: dict[str, Any]) -> dict[str, str | None]:
    raw = service.get("environment") or {}
    if isinstance(raw, dict):
        return {str(key): None if value is None else str(value) for key, value in raw.items()}
    if isinstance(raw, list):
        result: dict[str, str | None] = {}
        for item in raw:
            if not isinstance(item, str):
                continue
            key, separator, value = item.partition("=")
            result[key] = value if separator else None
        return result
    return {}


def _short_port(value: str) -> tuple[str, str, str, str]:
    protocol = "tcp"
    raw = value
    if "/" in raw:
        raw, protocol = raw.rsplit("/", 1)
    if raw.startswith("["):
        closing = raw.find("]")
        if closing < 0:
            raise DeploymentValidationError(f"porta IPv6 invalida: {value}")
        host = raw[1:closing]
        remainder = raw[closing + 1 :].lstrip(":")
        parts = remainder.split(":")
    else:
        parts = raw.split(":")
        host = "" if len(parts) < 3 else parts.pop(0)
    if len(parts) == 1:
        return host, "", parts[0], protocol
    if len(parts) == 2:
        return host, parts[0], parts[1], protocol
    raise DeploymentValidationError(f"porta Compose invalida: {value}")


def _ports(service: dict[str, Any], env: dict[str, str]) -> tuple[list[tuple[str, str, str, str]], list[str]]:
    result: list[tuple[str, str, str, str]] = []
    errors: list[str] = []
    raw_ports = service.get("ports") or []
    if not isinstance(raw_ports, list):
        return result, ["ports deve ser lista"]
    for raw in raw_ports:
        try:
            if isinstance(raw, str):
                result.append(_short_port(interpolate(raw, env)))
            elif isinstance(raw, dict):
                host = interpolate(str(raw.get("host_ip", "")), env)
                published = interpolate(str(raw.get("published", "")), env)
                target = interpolate(str(raw.get("target", "")), env)
                protocol = str(raw.get("protocol", "tcp"))
                result.append((host, published, target, protocol))
            else:
                errors.append(f"entrada de porta invalida: {raw!r}")
        except DeploymentValidationError as exc:
            errors.append(str(exc))
    return result, errors


def _explicit_resource_names(document: dict[str, Any], project: str, kind: str) -> dict[str, tuple[str, bool]]:
    result: dict[str, tuple[str, bool]] = {}
    resources = document.get(kind) or {}
    if not isinstance(resources, dict):
        return result
    for logical, config in resources.items():
        config = config if isinstance(config, dict) else {}
        external = bool(config.get("external"))
        name = str(config.get("name") or f"{project}_{logical}")
        result[str(logical)] = (name, external)
    return result


def _config_paths(root: Path, compose_path: Path, document: dict[str, Any], env: dict[str, str]) -> list[str]:
    errors: list[str] = []

    def require_path(raw: str, label: str, *, file_only: bool) -> None:
        try:
            rendered = interpolate(raw, env)
        except DeploymentValidationError as exc:
            errors.append(f"{label}: {exc}")
            return
        if rendered in {"/var/run/docker.sock", ".env", "./.env"}:
            return
        candidate = Path(rendered)
        if not candidate.is_absolute():
            candidate = (compose_path.parent / candidate).resolve()
        exists = candidate.is_file() if file_only else candidate.exists()
        if not exists:
            kind = "arquivo" if file_only else "caminho"
            errors.append(f"{label}: {kind} de configuracao ausente: {rendered}")

    for name, config in (document.get("configs") or {}).items():
        if isinstance(config, dict) and isinstance(config.get("file"), str):
            require_path(config["file"], f"config {name}", file_only=True)

    for service_name, service in (document.get("services") or {}).items():
        if not isinstance(service, dict):
            continue
        for entry in service.get("volumes") or []:
            source = target = ""
            if isinstance(entry, str):
                parts = entry.split(":")
                if len(parts) >= 2:
                    source, target = parts[0], parts[1]
            elif isinstance(entry, dict) and entry.get("type") == "bind":
                source = str(entry.get("source", ""))
                target = str(entry.get("target", ""))
            if not source or not target or source == "/var/run/docker.sock":
                continue
            # Diretorios de dados sao criados no host; mounts de configuracao
            # devem existir ja no pacote.
            suffix = PurePosixPath(target).suffix.lower()
            is_config_tree = PurePosixPath(source).parts[:2] == (".", "config") or source.startswith("./config/")
            if is_config_tree:
                require_path(source, f"servico {service_name}", file_only=False)
            elif suffix in {".yaml", ".yml", ".json", ".toml", ".conf", ".ini", ".alloy", ".template", ".sh"}:
                require_path(source, f"servico {service_name}", file_only=True)
    return errors


def _validate_manifest(
    root: Path,
    relative_path: Path,
    environment_name: str,
    env: dict[str, str],
) -> tuple[dict[str, Any], set[str], list[str], dict[str, Any]]:
    path = root / relative_path
    document, text, errors = _yaml_document(path)
    if not document:
        return document, set(), errors, {}
    services = document.get("services") or {}
    expected_app_env = EXPECTED_ENVIRONMENT[environment_name]["APP_ENV"]

    if "build:" in text or any(isinstance(service, dict) and "build" in service for service in services.values()):
        errors.append("build e proibido em deployment standalone; use somente imagens publicadas")
    forbidden_reference = "production" if environment_name == "develop" else "develop"
    if re.search(rf"compose[._/-]*{forbidden_reference}|deployments/{forbidden_reference}", text, re.I):
        errors.append(f"manifest {environment_name} referencia artefato de {forbidden_reference}")

    project = env.get("COMPOSE_PROJECT_NAME", "")
    try:
        compose_name = interpolate(str(document.get("name", "")), env)
    except DeploymentValidationError as exc:
        compose_name = ""
        errors.append(f"name: {exc}")
    if compose_name != project:
        errors.append(f"name Compose {compose_name!r} difere de COMPOSE_PROJECT_NAME={project!r}")

    registry = env.get("PIGE360_IMAGE_REGISTRY", "").rstrip("/")
    env_tag = env.get("PIGE360_IMAGE_TAG", "")
    images: set[str] = set()
    resolved_images: dict[str, str] = {}
    published_ports: dict[tuple[str, str, str], str] = {}

    for service_name, raw_service in services.items():
        if not isinstance(raw_service, dict):
            errors.append(f"servico {service_name} deve ser objeto")
            continue
        image_value = raw_service.get("image")
        if not isinstance(image_value, str) or not image_value.strip():
            errors.append(f"servico {service_name} sem image explicita")
            continue
        try:
            resolved_image = interpolate(image_value, env)
        except DeploymentValidationError as exc:
            errors.append(f"servico {service_name}: {exc}")
            continue
        resolved_images[str(service_name)] = resolved_image
        if not resolved_image.strip():
            errors.append(f"servico {service_name}: image resolveu para valor vazio")
            continue
        image_name = _normal_image_name(resolved_image)
        tag, digest = _image_tag(resolved_image)
        if digest is not None and not DIGEST_RE.fullmatch(digest):
            errors.append(f"servico {service_name}: digest invalido: {digest}")
        if environment_name == "production" and digest is None:
            if tag is None or tag.lower() in MOVING_PRODUCTION_TAGS:
                errors.append(f"servico {service_name}: tag movel/ausente proibida em producao: {resolved_image}")
        if image_name.startswith("pige360-"):
            images.add(image_name)
            if not registry or not resolved_image.startswith(registry + "/"):
                errors.append(f"servico {service_name}: imagem first-party fora do registry: {resolved_image}")
            if environment_name == "develop":
                if digest is None and tag != env_tag:
                    errors.append(
                        f"servico {service_name}: tag {tag!r} difere da tag develop declarada {env_tag!r}"
                    )
            else:
                if digest is not None:
                    if not DIGEST_RE.fullmatch(digest):
                        errors.append(f"servico {service_name}: digest de producao invalido: {digest}")
                elif tag is None or not STABLE_SEMVER_RE.fullmatch(tag) or tag.lower() in MOVING_PRODUCTION_TAGS:
                    errors.append(f"servico {service_name}: referencia de producao nao imutavel: {resolved_image}")
                elif tag != env_tag:
                    errors.append(
                        f"servico {service_name}: tag {tag!r} difere da tag de producao declarada {env_tag!r}"
                    )
            try:
                pull_policy = interpolate(str(raw_service.get("pull_policy", "")), env)
            except DeploymentValidationError as exc:
                errors.append(f"servico {service_name}: pull_policy invalida: {exc}")
            else:
                if pull_policy != "always":
                    errors.append(
                        f"servico {service_name}: pull_policy='always' obrigatoria, recebeu {pull_policy!r}"
                    )

        service_env = _service_environment(raw_service)
        if "APP_ENV" in service_env:
            raw_app_env = service_env["APP_ENV"]
            try:
                app_env = interpolate(raw_app_env or env.get("APP_ENV", ""), env)
            except DeploymentValidationError as exc:
                errors.append(f"servico {service_name}: APP_ENV invalido: {exc}")
            else:
                if app_env != expected_app_env:
                    errors.append(
                        f"servico {service_name}: APP_ENV={app_env!r}; esperado {expected_app_env!r}"
                    )

        if image_name.startswith("pige360-"):
            entries = _env_file_entries(raw_service)
            resolved_entries: list[str] = []
            for entry in entries:
                try:
                    resolved_entries.append(interpolate(entry, env))
                except DeploymentValidationError as exc:
                    errors.append(f"servico {service_name}: env_file invalido: {exc}")
            if not any(PurePosixPath(entry).name == ".env" for entry in resolved_entries):
                errors.append(f"servico {service_name}: env_file .env obrigatorio")

        service_ports, port_errors = _ports(raw_service, env)
        errors.extend(f"servico {service_name}: {item}" for item in port_errors)
        if service_ports and INTERNAL_SERVICE_RE.search(str(service_name)):
            errors.append(f"servico interno {service_name} nao pode publicar portas")
        for host, published, target, protocol in service_ports:
            if not published:
                errors.append(f"servico {service_name}: porta {target} sem published explicito")
                continue
            try:
                if not 1 <= int(published) <= 65535 or not 1 <= int(target) <= 65535:
                    raise ValueError
            except ValueError:
                errors.append(f"servico {service_name}: porta invalida {host}:{published}:{target}")
            if EDGE_SERVICE_RE.search(str(service_name)):
                if target not in {"80", "443"}:
                    errors.append(f"servico edge {service_name}: target publico inesperado: {target}")
            elif LOOPBACK_PUBLISHABLE_RE.search(str(service_name)):
                if host not in {"127.0.0.1", "::1"}:
                    errors.append(f"servico {service_name}: bind deve ser loopback, recebido {host!r}")
            else:
                errors.append(f"servico {service_name} nao esta autorizado a publicar portas")
            key = (host, published, protocol)
            previous = published_ports.get(key)
            if previous and previous != str(service_name):
                errors.append(
                    f"porta publicada duplicada {host}:{published}/{protocol}: {previous} e {service_name}"
                )
            published_ports[key] = str(service_name)

    gateway_publishers = {
        service for service in published_ports.values() if "gateway" in service
    }
    non_gateway_publishers = {
        service for service in published_ports.values() if "gateway" not in service
    }
    if gateway_publishers and non_gateway_publishers:
        errors.append(
            "quando o gateway publica a entrada standalone, nenhum outro servico pode publicar porta: "
            f"gateway={sorted(gateway_publishers)}, outros={sorted(non_gateway_publishers)}"
        )

    errors.extend(_config_paths(root, path, document, env))
    details = {
        "path": relative_path.as_posix(),
        "services": len(services),
        "first_party_images": sorted(images),
        "resolved_images": resolved_images,
        "published_ports": [
            {"host": host, "published": published, "protocol": protocol, "service": service}
            for (host, published, protocol), service in sorted(published_ports.items())
        ],
    }
    return document, images, errors, details


def validate(source_root: Path) -> dict[str, Any]:
    root = source_root.resolve()
    checks: list[dict[str, Any]] = []
    all_required_paths = [
        Path("VERSION"),
        *(path for pair in ENVIRONMENT_FILES.values() for path in pair),
        *(path for _, path in VARIANT_FILES.values()),
        Path("deploy/images/catalog.yaml"),
    ]
    missing = [path.as_posix() for path in all_required_paths if not (root / path).is_file()]
    _add(checks, "deployment-files", [f"arquivo obrigatorio ausente: {path}" for path in missing], {
        "required": [path.as_posix() for path in all_required_paths],
        "missing": missing,
    })

    environments: dict[str, dict[str, str]] = {}
    env_errors: list[str] = []
    version_path = root / "VERSION"
    project_version = version_path.read_text(encoding="utf-8").strip() if version_path.is_file() else ""
    if project_version and not STABLE_SEMVER_RE.fullmatch(project_version):
        env_errors.append(f"VERSION deve conter SemVer estavel, recebeu {project_version!r}")
    for name, (_, relative_env) in ENVIRONMENT_FILES.items():
        values, errors = load_env(root / relative_env)
        environments[name] = values
        env_errors.extend(f"{relative_env}: {error}" for error in errors)
        missing_keys = sorted(REQUIRED_ENV_KEYS - set(values))
        empty_keys = sorted(key for key in REQUIRED_ENV_KEYS if key in values and not values[key])
        env_errors.extend(f"{relative_env}: chave obrigatoria ausente: {key}" for key in missing_keys)
        env_errors.extend(f"{relative_env}: chave obrigatoria vazia: {key}" for key in empty_keys)
        for label, aliases in REQUIRED_ENV_ALIASES.items():
            present = [key for key in aliases if key in values]
            if not present:
                env_errors.append(
                    f"{relative_env}: {label} ausente; use uma de {', '.join(aliases)}"
                )
            elif not any(values[key] for key in present):
                env_errors.append(f"{relative_env}: {label} esta vazio")
        for key, expected in EXPECTED_ENVIRONMENT[name].items():
            if values.get(key) != expected:
                env_errors.append(f"{relative_env}: {key}={values.get(key)!r}; esperado {expected!r}")
        registry = values.get("PIGE360_IMAGE_REGISTRY", "")
        if registry.startswith(("http://", "https://")) or registry.endswith("/"):
            env_errors.append(f"{relative_env}: PIGE360_IMAGE_REGISTRY deve ser host/path sem protocolo ou / final")
        tag = values.get("PIGE360_IMAGE_TAG", "")
        app_version = values.get("APP_VERSION", "")
        if project_version and app_version != project_version:
            env_errors.append(
                f"{relative_env}: APP_VERSION={app_version!r} difere de VERSION={project_version!r}"
            )
        if name == "develop" and not DEVELOP_TAG_RE.fullmatch(tag):
            env_errors.append(f"{relative_env}: tag develop invalida: {tag!r}")
        if name == "production" and (
            not STABLE_SEMVER_RE.fullmatch(tag) or tag.lower() in MOVING_PRODUCTION_TAGS
        ):
            env_errors.append(f"{relative_env}: producao exige tag SemVer estavel, recebeu {tag!r}")
        if name == "production" and tag and values.get("APP_VERSION") != tag:
            env_errors.append(
                f"{relative_env}: APP_VERSION={values.get('APP_VERSION')!r} difere de PIGE360_IMAGE_TAG={tag!r}"
            )
        console_host_key = "CONSOLE_BIND_HOST" if "CONSOLE_BIND_HOST" in values else "CONTROL_WEB_BIND_HOST"
        bind_host_keys = ("WEB_BIND_HOST", console_host_key, "BRANDING_BIND_HOST", "DOWNLOADS_BIND_HOST")
        if "GATEWAY_BIND_HOST" in values:
            bind_host_keys = ("GATEWAY_BIND_HOST",)
        for key in bind_host_keys:
            if values.get(key) not in {"127.0.0.1", "::1"}:
                env_errors.append(f"{relative_env}: {key} deve usar loopback")
        web_port_key = "WEB_BIND_PORT" if "WEB_BIND_PORT" in values else "WEB_PUBLISHED_PORT"
        console_port_key = "CONSOLE_BIND_PORT" if "CONSOLE_BIND_PORT" in values else "CONTROL_WEB_PUBLISHED_PORT"
        branding_port_key = "BRANDING_BIND_PORT" if "BRANDING_BIND_PORT" in values else "BRANDING_PUBLISHED_PORT"
        downloads_port_key = "DOWNLOADS_BIND_PORT" if "DOWNLOADS_BIND_PORT" in values else "DOWNLOADS_PUBLISHED_PORT"
        port_keys = (web_port_key, console_port_key, branding_port_key, downloads_port_key)
        if "GATEWAY_PORT" in values:
            port_keys = ("GATEWAY_PORT",)
        seen_ports: dict[str, str] = {}
        for key in port_keys:
            value = values.get(key, "")
            try:
                if not 1 <= int(value) <= 65535:
                    raise ValueError
            except ValueError:
                env_errors.append(f"{relative_env}: {key} invalida: {value!r}")
                continue
            if value in seen_ports:
                env_errors.append(f"{relative_env}: porta {value} repetida em {seen_ports[value]} e {key}")
            seen_ports[value] = key
    if environments.get("develop") and environments.get("production"):
        if set(environments["develop"]) != set(environments["production"]):
            env_errors.append(
                "env develop/production possuem chaves divergentes: "
                f"so_develop={sorted(set(environments['develop']) - set(environments['production']))}; "
                f"so_production={sorted(set(environments['production']) - set(environments['develop']))}"
            )
        for key in ("COMPOSE_PROJECT_NAME",):
            develop_value = environments["develop"].get(key)
            production_value = environments["production"].get(key)
            if develop_value == production_value:
                env_errors.append(f"develop e production nao podem compartilhar {key}={develop_value!r}")
    _add(checks, "environment-contract", env_errors, {
        name: {
            key: values.get(key)
            for key in sorted(REQUIRED_ENV_KEYS | {item for aliases in REQUIRED_ENV_ALIASES.values() for item in aliases})
            if key in values
        }
        for name, values in environments.items()
    })

    catalog, required_catalog, catalog_errors = _catalog_images(root)
    _add(checks, "image-catalog", catalog_errors, {
        "available": sorted(catalog),
        "required": sorted(required_catalog),
    })

    manifests: dict[str, dict[str, Any]] = {}
    manifest_images: dict[str, set[str]] = {}
    manifest_details: dict[str, Any] = {}
    for environment_name, (compose_path, _) in ENVIRONMENT_FILES.items():
        document, images, errors, details = _validate_manifest(
            root, compose_path, environment_name, environments.get(environment_name, {})
        )
        manifests[environment_name] = document
        manifest_images[environment_name] = images
        manifest_details[environment_name] = details
        _add(checks, f"compose-{environment_name}", errors, details)

    for variant_name, (environment_name, compose_path) in VARIANT_FILES.items():
        _, images, errors, details = _validate_manifest(
            root, compose_path, environment_name, environments.get(environment_name, {})
        )
        manifest_images[variant_name] = images
        manifest_details[variant_name] = details
        canonical_images = manifest_images.get(environment_name, set())
        if images != canonical_images:
            errors.append(
                f"imagens first-party divergem do compose {environment_name}: "
                f"ausentes={sorted(canonical_images - images)}, extras={sorted(images - canonical_images)}"
            )
        _add(checks, f"compose-{variant_name}", errors, details)

    parity_errors: list[str] = []
    develop_images = manifest_images.get("develop", set())
    production_images = manifest_images.get("production", set())
    if develop_images != production_images:
        parity_errors.append(
            "develop e production consomem imagens first-party diferentes: "
            f"so_develop={sorted(develop_images - production_images)}, "
            f"so_production={sorted(production_images - develop_images)}"
        )
    for name, images in manifest_images.items():
        unknown = images - catalog
        missing_required = required_catalog - images
        if unknown:
            parity_errors.append(f"{name}: imagens ausentes do catalogo: {sorted(unknown)}")
        if missing_required:
            parity_errors.append(f"{name}: imagens obrigatorias do catalogo nao consumidas: {sorted(missing_required)}")
    _add(checks, "deployment-image-parity", parity_errors, {
        "catalog": sorted(catalog),
        "required_catalog": sorted(required_catalog),
        "manifests": {name: sorted(images) for name, images in manifest_images.items()},
    })

    isolation_errors: list[str] = []
    if manifests.get("develop") and manifests.get("production"):
        develop_project = environments.get("develop", {}).get("COMPOSE_PROJECT_NAME", "")
        production_project = environments.get("production", {}).get("COMPOSE_PROJECT_NAME", "")
        for kind in ("volumes", "networks"):
            develop_resources = _explicit_resource_names(manifests["develop"], develop_project, kind)
            production_resources = _explicit_resource_names(manifests["production"], production_project, kind)
            develop_names = {name for name, external in develop_resources.values() if not external}
            production_names = {name for name, external in production_resources.values() if not external}
            overlap = sorted(develop_names & production_names)
            if overlap:
                isolation_errors.append(f"{kind} internos compartilhados entre develop e production: {overlap}")
    _add(checks, "environment-isolation", isolation_errors)

    failures = [check for check in checks if check["status"] == "failed"]
    return {
        "schema_version": 1,
        "status": "failed" if failures else "passed",
        "source_root": str(root),
        "checks": checks,
        "failed_checks": [check["name"] for check in failures],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="raiz do fonte PIGE360",
    )
    parser.add_argument("--output", type=Path, help="grava tambem o relatorio JSON neste caminho")
    args = parser.parse_args(argv)
    report = validate(args.source_root)
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    sys.stdout.write(rendered)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
