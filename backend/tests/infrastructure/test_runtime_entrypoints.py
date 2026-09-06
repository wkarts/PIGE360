from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_web_nginx_keeps_api_on_the_browser_origin_and_preserves_routing_headers() -> None:
    nginx = (ROOT / "infra/docker/nginx.conf").read_text(encoding="utf-8")

    assert "location ^~ /api/" in nginx
    assert "proxy_pass http://pige360-api:8000;" in nginx
    assert "proxy_set_header Host $http_host;" in nginx
    assert "proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;" in nginx
    assert "proxy_set_header X-Forwarded-Proto $scheme;" in nginx
    assert "proxy_set_header X-Correlation-ID $http_x_correlation_id;" in nginx
    assert "client_max_body_size 32m;" in nginx


def test_web_nginx_does_not_publish_internal_prometheus_metrics() -> None:
    nginx = (ROOT / "infra/docker/nginx.conf").read_text(encoding="utf-8")
    metrics_location = "location = /api/v1/metrics { access_log off; return 404; }"

    assert metrics_location in nginx
    assert nginx.index(metrics_location) < nginx.index("location ^~ /api/")


def test_api_image_prepares_tenant_storage_for_the_unprivileged_runtime_user() -> None:
    dockerfile = (ROOT / "infra/docker/Dockerfile.api").read_text(encoding="utf-8")

    assert "mkdir -p /var/lib/pige360/control /var/lib/pige360/tenants" in dockerfile
    assert "chown -R 10001:10001 /var/lib/pige360" in dockerfile
    assert "APP_STORAGE_ROOT=/var/lib/pige360/tenants" in dockerfile
    assert dockerfile.rstrip().splitlines()[-2] == "EXPOSE 8000"
    assert "--forwarded-allow-ips" in dockerfile
    assert "${TRUSTED_PROXY_CIDRS:-127.0.0.1/32}" in dockerfile


def test_web_image_oci_labels_identify_the_built_application_variant() -> None:
    dockerfile = (ROOT / "infra/docker/Dockerfile.web").read_text(encoding="utf-8")

    assert "ARG IMAGE_NAME=pige360-web" in dockerfile
    assert 'org.opencontainers.image.title="${IMAGE_NAME}"' in dockerfile
    assert 'io.pige360.runtime.role="web"' in dockerfile
    assert 'io.pige360.web.application="${APP_DIR}"' in dockerfile
