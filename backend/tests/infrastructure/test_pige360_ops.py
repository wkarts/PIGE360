from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("pige360_ops", ROOT / "infra/ops/pige360_ops.py")
assert SPEC and SPEC.loader
OPS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(OPS)


def test_secret_initialization_is_idempotent_and_external_secrets_start_empty(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(OPS, "SECRETS_ROOT", tmp_path)
    args = argparse.Namespace()
    assert OPS.init_secrets(args) == 0
    first = {path.name: path.read_bytes() for path in tmp_path.iterdir()}
    assert set(first) == {f"{name}.txt" for name in OPS.ALL_SECRETS}
    assert all(first[f"{name}.txt"] for name in OPS.INTERNAL_SECRETS + OPS.SPECIAL_SECRETS)
    assert all(first[f"{name}.txt"] == b"" for name in OPS.EXTERNAL_SECRETS)
    assert OPS.init_secrets(args) == 0
    assert first == {path.name: path.read_bytes() for path in tmp_path.iterdir()}


def test_external_secret_set_uses_stdin_and_rejects_internal_rotation(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(OPS, "SECRETS_ROOT", tmp_path)
    OPS.init_secrets(argparse.Namespace())
    monkeypatch.setattr(OPS.sys, "stdin", type("Input", (), {"buffer": type("Buffer", (), {"read": lambda self, _: b"token-value\n"})()})())
    assert OPS.secret_set(argparse.Namespace(name="cloudflare_api_token")) == 0
    assert (tmp_path / "cloudflare_api_token.txt").read_text() == "token-value\n"
    with pytest.raises(OPS.OperationError, match="somente secrets externos"):
        OPS.secret_set(argparse.Namespace(name="app_jwt_secret"))


def test_configuration_validation_enforces_environment_tag_policy(tmp_path: Path, monkeypatch) -> None:
    secrets = tmp_path / "secrets"
    config = tmp_path / "config"
    monkeypatch.setattr(OPS, "SECRETS_ROOT", secrets)
    monkeypatch.setattr(OPS, "CONFIG_ROOT", config)
    OPS.init_secrets(argparse.Namespace())
    for relative in (
        "gateway/default.conf.template",
        "observability/prometheus.yml",
        "observability/loki.yaml",
        "observability/alloy.config",
        "init-minio.sh",
    ):
        target = config / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("valid\n")
    values = {
        "PIGE360_ENVIRONMENT": "production",
        "PIGE360_IMAGE_TAG": "1.1.1",
        "APP_VERSION": "1.1.1",
        "PIGE360_BASE_DOMAIN": "pige360.com.br",
        "PLATFORM_API_HOST": "api.pige360.com.br",
        "PLATFORM_CONSOLE_HOST": "console.pige360.com.br",
        "PLATFORM_BRANDING_HOST": "branding.pige360.com.br",
        "PLATFORM_DOWNLOADS_HOST": "downloads.pige360.com.br",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    assert OPS.validate_config(argparse.Namespace()) == 0
    monkeypatch.setenv("PIGE360_IMAGE_TAG", "develop")
    with pytest.raises(OPS.OperationError, match="produção exige"):
        OPS.validate_config(argparse.Namespace())


def test_migration_services_are_split_and_honor_skip(monkeypatch) -> None:
    commands: list[list[str]] = []
    monkeypatch.setattr(OPS, "_run", lambda command, **_: commands.append(list(command)))
    monkeypatch.setenv("PIGE360_SKIP_MIGRATIONS", "false")
    monkeypatch.setenv("PIGE360_SKIP_TENANT_MIGRATIONS", "false")
    OPS.migrate_control(argparse.Namespace())
    OPS.migrate_tenants(argparse.Namespace())
    assert commands == [
        ["python", "-m", "alembic", "-c", "backend/alembic_control/alembic.ini", "upgrade", "head"],
        ["python", "-m", "app.shared.database.migrate_tenants"],
    ]
    commands.clear()
    monkeypatch.setenv("PIGE360_SKIP_MIGRATIONS", "true")
    OPS.migrate_control(argparse.Namespace())
    OPS.migrate_tenants(argparse.Namespace())
    assert commands == []
