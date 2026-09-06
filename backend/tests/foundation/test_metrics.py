from __future__ import annotations

import re
from pathlib import Path

from app.main import create_app
from app.bootstrap.config import Settings


PLATFORM_HOST = "api.platform.local"
VERSION = (Path(__file__).resolve().parents[3] / "VERSION").read_text(encoding="utf-8").strip()


def test_metrics_exposes_real_process_and_http_samples_without_authentication(local_env) -> None:
    live = local_env.client.get("/api/v1/health/live", headers={"host": PLATFORM_HOST})
    assert live.status_code == 200

    response = local_env.client.get("/api/v1/metrics", headers={"host": PLATFORM_HOST})

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/plain; version=0.0.4; charset=utf-8"
    assert response.headers["cache-control"] == "no-store"
    assert f'pige360_build_info{{environment="testing",version="{VERSION}"}} 1' in response.text
    assert re.search(r"^pige360_process_uptime_seconds [0-9]+(?:\.[0-9]+)?$", response.text, re.MULTILINE)
    assert re.search(
        r'^pige360_http_requests_total\{method="GET",status_code="200"\} [1-9][0-9]*$',
        response.text,
        re.MULTILINE,
    )
    assert "tenant_id=" not in response.text
    assert "request_path=" not in response.text


def test_metrics_counts_requests_rejected_before_route_resolution(local_env) -> None:
    rejected = local_env.client.get(
        "/api/v1/health/live",
        headers={"host": "unknown.invalid"},
    )
    assert rejected.status_code == 404

    response = local_env.client.get("/api/v1/metrics", headers={"host": PLATFORM_HOST})

    assert response.status_code == 200
    assert re.search(
        r'^pige360_http_requests_total\{method="GET",status_code="404"\} [1-9][0-9]*$',
        response.text,
        re.MULTILINE,
    )


def test_metrics_operational_route_is_not_added_to_public_openapi(tmp_path) -> None:
    app = create_app(Settings().testing(tmp_path / "runtime"))

    assert "/api/v1/metrics" not in app.openapi()["paths"]
