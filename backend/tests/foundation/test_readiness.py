from __future__ import annotations

import time
from dataclasses import replace
from pathlib import Path

from fastapi.testclient import TestClient

from app.bootstrap.config import Settings
from app.main import create_app
from app.modules.foundation.application.readiness import build_readiness_report


PLATFORM_HOST = "api.platform.local"


def _check(body: dict, name: str) -> list[dict]:
    return [item for item in body["checks"] if item["name"] == name]


def test_live_is_light_and_local_readiness_checks_catalog_and_tenants(local_env):
    local_env.client.app.state.readiness_probes = {
        "redis": lambda _context: (_ for _ in ()).throw(AssertionError("live não deve sondar Redis"))
    }
    live = local_env.client.get("/api/v1/health/live", headers={"host": PLATFORM_HOST})
    assert live.status_code == 200 and live.json() == {"status": "ok"}

    ready = local_env.client.get("/api/v1/health/ready", headers={"host": PLATFORM_HOST})
    assert ready.status_code == 200, ready.text
    body = ready.json()
    assert body["status"] == "ready"
    assert body["summary"]["active_tenants"] == 2
    assert _check(body, "control_database")[0]["status"] == "pass"
    assert _check(body, "control_migrations")[0]["details"]["mode"] == "local_schema_bootstrap"
    assert len(_check(body, "tenant_database")) == 2
    assert all(item["status"] == "pass" for item in _check(body, "tenant_database"))


def test_required_injected_probe_failure_returns_503_without_leaking_message(tmp_path: Path):
    settings = replace(
        Settings().testing(tmp_path / "runtime"),
        readiness_require_redis=True,
        readiness_timeout_seconds=0.1,
    )
    app = create_app(settings)
    app.state.readiness_probes = {
        "redis": lambda _context: (_ for _ in ()).throw(
            RuntimeError("redis://user:password@internal.example/0")
        )
    }
    with TestClient(app) as client:
        response = client.get("/api/v1/health/ready", headers={"host": PLATFORM_HOST})
    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
    redis_check = _check(response.json(), "redis")[0]
    assert redis_check["critical"] is True
    assert redis_check["details"] == {"code": "RuntimeError"}
    assert "password" not in response.text


def test_probe_timeout_is_fail_closed_when_dependency_is_required(tmp_path: Path):
    settings = replace(
        Settings().testing(tmp_path / "runtime"),
        readiness_require_rabbitmq=True,
        readiness_timeout_seconds=0.1,
    )
    app = create_app(settings)

    def slow(_context):
        time.sleep(0.4)
        return {"ready": True}

    app.state.readiness_probes = {"rabbitmq": slow}
    with TestClient(app) as client:
        started = time.perf_counter()
        response = client.get("/api/v1/health/ready", headers={"host": PLATFORM_HOST})
        elapsed = time.perf_counter() - started
    assert response.status_code == 503
    assert elapsed < 0.35
    assert _check(response.json(), "rabbitmq")[0]["details"] == {"code": "timeout"}


class _ProductionControl:
    def __init__(self, revision: str):
        self.revision = revision

    def scalar(self, sql: str, _params=()):
        if "alembic_version" in sql:
            return self.revision
        return 1

    def fetch_all(self, _sql: str, _params=()):
        return []


class _ProductionRouter:
    def __init__(self, revision: str):
        self.control = _ProductionControl(revision)


def test_production_forces_dependencies_to_be_critical_even_if_flags_are_false():
    settings = Settings(environment="production", readiness_timeout_seconds=0.1)
    router = _ProductionRouter("0007_commercial_administration")
    report = build_readiness_report(
        router,  # type: ignore[arg-type]
        settings,
        probes={"redis": lambda _context: False, "rabbitmq": lambda _context: False, "minio": lambda _context: False},
    )
    assert report["status"] == "not_ready"
    for name in ("redis", "rabbitmq", "minio"):
        item = _check(report, name)[0]
        assert item["critical"] is True and item["status"] == "fail"


def test_production_rejects_control_database_behind_alembic_head():
    settings = Settings(environment="production", readiness_timeout_seconds=0.1)
    router = _ProductionRouter("0001_control_plane")
    report = build_readiness_report(
        router,  # type: ignore[arg-type]
        settings,
        probes={"redis": lambda _context: True, "rabbitmq": lambda _context: True, "minio": lambda _context: True},
    )
    migration = _check(report, "control_migrations")[0]
    assert report["status"] == "not_ready"
    assert migration["status"] == "fail"
    assert migration["details"] == {"code": "control_migration_not_at_head"}
