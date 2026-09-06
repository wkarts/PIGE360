from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from app.bootstrap.config import Settings
from app.shared.domain.ids import iso_now


def _enabled(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _secret_configured(direct_name: str, file_name: str) -> bool:
    if bool(os.getenv(direct_name, "")):
        return True
    candidate = os.getenv(file_name, "").strip()
    if not candidate:
        return False
    try:
        path = Path(candidate)
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


def _provider(
    code: str,
    category: str,
    *,
    enabled: bool,
    configured: bool,
    local_fallback: bool = False,
) -> dict[str, Any]:
    if local_fallback:
        state = "local_fallback"
    elif not enabled:
        state = "disabled"
    elif configured:
        state = "configured_not_probed"
    else:
        state = "configuration_incomplete"
    return {
        "code": code,
        "category": category,
        "enabled": enabled,
        "configured": configured,
        "state": state,
        "status_source": "configuration_only",
        "external_probe_performed": False,
    }


def sanitized_provider_catalog(settings: Settings) -> dict[str, Any]:
    production = settings.environment in {"production", "staging"}
    cloudflare_enabled = any(
        _enabled(name)
        for name in ("CLOUDFLARE_ENABLED", "CLOUDFLARE_SAAS_ENABLED", "CLOUDFLARE_TUNNELS_ENABLED")
    )
    cloudflare_configured = bool(
        os.getenv("CLOUDFLARE_TENANT_ZONE_ID", "").strip()
        and _secret_configured("CLOUDFLARE_API_TOKEN", "CLOUDFLARE_API_TOKEN_FILE")
    )
    connect_enabled = _enabled("CONNECT_API_ENABLED")
    connect_configured = bool(
        os.getenv("CONNECT_API_BASE_URL", "").strip()
        and _secret_configured("CONNECT_API_KEY", "CONNECT_API_KEY_FILE")
    )
    loki_enabled = _enabled("LOKI_ENABLED", bool(os.getenv("LOKI_INTERNAL_URL", "").strip()))

    providers = [
        _provider(
            "control_database",
            "database",
            enabled=True,
            configured=(bool(settings.database_control_url and settings.database_control_password) if production else True),
            local_fallback=not production,
        ),
        _provider(
            "tenant_database",
            "database",
            enabled=True,
            configured=(
                bool(
                    settings.database_tenant_admin_url
                    and settings.database_tenant_admin_password
                    and settings.database_secret_key
                )
                if production
                else True
            ),
            local_fallback=not production,
        ),
        _provider(
            "object_storage",
            "storage",
            enabled=True,
            configured=(
                bool(
                    settings.object_storage_endpoint
                    and settings.object_storage_access_key
                    and settings.object_storage_secret_key
                )
                if production
                else True
            ),
            local_fallback=not production,
        ),
        _provider(
            "redis",
            "queue_cache",
            enabled=bool(settings.redis_url),
            configured=bool(settings.redis_url and settings.redis_password),
        ),
        _provider(
            "rabbitmq",
            "queue_cache",
            enabled=bool(settings.rabbitmq_url),
            configured=bool(settings.rabbitmq_url and settings.rabbitmq_password),
        ),
        _provider(
            "cloudflare",
            "dns_tls",
            enabled=cloudflare_enabled,
            configured=cloudflare_configured,
        ),
        _provider(
            "loki",
            "observability",
            enabled=loki_enabled,
            configured=bool(os.getenv("LOKI_INTERNAL_URL", "").strip()),
        ),
        _provider(
            "connect_api",
            "communication",
            enabled=connect_enabled,
            configured=connect_configured,
        ),
        _provider(
            "mail",
            "communication",
            enabled=settings.mail_mode != "disabled",
            configured=bool(settings.mail_imap_host and settings.mail_smtp_host),
        ),
    ]
    return {
        "status_scope": "configuration_only",
        "external_probe_performed": False,
        "generated_at": iso_now(),
        "items": providers,
    }
