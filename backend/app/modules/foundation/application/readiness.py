from __future__ import annotations

import os
import time
from concurrent.futures import Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.request import Request, urlopen

from alembic.config import Config
from alembic.script import ScriptDirectory

from app.bootstrap.config import Settings
from app.shared.database.router import DataRouter
from app.shared.domain.ids import iso_now


Probe = Callable[["ProbeContext"], Any]
ProbeRegistry = Mapping[str, Probe]


class ProbeFailure(RuntimeError):
    """Falha operacional cujo código pode ser exposto sem vazar DSN/segredo."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class ProbeContext:
    name: str
    timeout_seconds: float
    router: DataRouter
    settings: Settings
    tenant: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class CheckSpec:
    name: str
    critical: bool
    probe: Probe
    tenant: dict[str, Any] | None = None


_REDACTED_KEYS = ("secret", "password", "token", "credential", "dsn", "url", "endpoint", "key")


def _public(value: Any) -> Any:
    """Limita o resultado do probe a dados operacionais e remove chaves sensíveis."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_public(item) for item in value]
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for raw_key, item in value.items():
            key = str(raw_key)
            if key.startswith("_internal_"):
                continue
            if any(marker in key.lower() for marker in _REDACTED_KEYS):
                continue
            result[key] = _public(item)
        return result
    return type(value).__name__


def _alembic_head(directory: str) -> str:
    backend_root = Path(__file__).resolve().parents[4]
    script_location = backend_root / directory
    config = Config()
    config.set_main_option("script_location", str(script_location))
    head = ScriptDirectory.from_config(config).get_current_head()
    if not head:
        raise ProbeFailure("migration_head_missing")
    return str(head)


def _control_database(context: ProbeContext) -> dict[str, Any]:
    if context.router.control.scalar("SELECT 1") != 1:
        raise ProbeFailure("control_database_query_failed")
    return {"query": "ok"}


def _control_migrations(context: ProbeContext) -> dict[str, Any]:
    if context.settings.environment not in {"production", "staging"}:
        # O adapter SQLite local nasce do schema canônico e não usa Alembic.
        context.router.control.scalar("SELECT COUNT(*) FROM platform_tenants")
        return {"mode": "local_schema_bootstrap"}
    expected = _alembic_head("alembic_control")
    actual = context.router.control.scalar("SELECT version_num FROM alembic_version")
    if str(actual or "") != expected:
        raise ProbeFailure("control_migration_not_at_head")
    return {"revision": actual}


def _tenant_catalog(context: ProbeContext) -> dict[str, Any]:
    rows = context.router.control.fetch_all(
        "SELECT id,code,status FROM platform_tenants WHERE status='active' ORDER BY id"
    )
    return {"active": len(rows), "_internal_tenants": rows}


def _tenant_database(context: ProbeContext) -> dict[str, Any]:
    tenant = context.tenant or {}
    tenant_id = str(tenant.get("id") or "")
    if not tenant_id:
        raise ProbeFailure("tenant_id_missing")
    store = context.router.tenant_store(tenant_id)
    if store.scalar("SELECT 1") != 1:
        raise ProbeFailure("tenant_database_query_failed")
    if context.settings.environment in {"production", "staging"}:
        expected = _alembic_head("alembic_tenant")
        actual = store.scalar("SELECT version_num FROM alembic_version")
        if str(actual or "") != expected:
            raise ProbeFailure("tenant_migration_not_at_head")
        migration = str(actual)
    else:
        store.scalar("SELECT COUNT(*) FROM tenant_metadata")
        migration = "local_schema_bootstrap"
    return {"migration": migration}


def _tenant_storage(context: ProbeContext) -> dict[str, Any]:
    tenant = context.tenant or {}
    tenant_id = str(tenant.get("id") or "")
    storage = context.router.object_storage(tenant_id)
    client = getattr(storage, "client", None)
    bucket = getattr(storage, "bucket", None)
    if client is not None and bucket:
        client.head_bucket(Bucket=bucket)
        return {"provider": "s3", "accessible": True}
    root = getattr(storage, "root", None)
    if root is None or not Path(root).is_dir() or not os.access(root, os.R_OK | os.W_OK | os.X_OK):
        raise ProbeFailure("local_tenant_storage_not_accessible")
    return {"provider": "local", "accessible": True}


def _redis(context: ProbeContext) -> dict[str, Any]:
    if not context.settings.redis_url:
        raise ProbeFailure("redis_not_configured")
    try:
        import redis
    except ImportError as exc:  # pragma: no cover - depende da imagem de produção
        raise ProbeFailure("redis_client_unavailable") from exc
    client = redis.Redis.from_url(
        context.settings.redis_url,
        password=context.settings.redis_password or None,
        socket_connect_timeout=context.timeout_seconds,
        socket_timeout=context.timeout_seconds,
    )
    try:
        if client.ping() is not True:
            raise ProbeFailure("redis_ping_failed")
    finally:
        client.close()
    return {"ping": "ok"}


def _rabbitmq(context: ProbeContext) -> dict[str, Any]:
    if not context.settings.rabbitmq_url:
        raise ProbeFailure("rabbitmq_not_configured")
    try:
        from kombu import Connection
    except ImportError as exc:  # pragma: no cover - depende da imagem de produção
        raise ProbeFailure("rabbitmq_client_unavailable") from exc
    connection = Connection(
        context.settings.rabbitmq_url,
        password=context.settings.rabbitmq_password or None,
        connect_timeout=context.timeout_seconds,
    )
    try:
        connection.ensure_connection(max_retries=0, timeout=context.timeout_seconds)
    finally:
        connection.release()
    return {"connection": "ok"}


def _minio(context: ProbeContext) -> dict[str, Any]:
    endpoint = context.settings.object_storage_endpoint.rstrip("/")
    if not endpoint:
        raise ProbeFailure("object_storage_not_configured")
    request = Request(f"{endpoint}/minio/health/ready", method="GET")
    with urlopen(request, timeout=context.timeout_seconds) as response:  # noqa: S310 - endpoint é configuração interna
        if not 200 <= int(response.status) < 300:
            raise ProbeFailure("minio_readiness_failed")
    return {"health": "ok"}


def _normalize_probe_result(value: Any) -> tuple[str, dict[str, Any]]:
    if value is False:
        return "fail", {"code": "probe_returned_false"}
    if isinstance(value, Mapping) and value.get("ready") is False:
        return "fail", dict(value)
    return "pass", dict(value) if isinstance(value, Mapping) else {}


def _run_specs(
    specs: list[CheckSpec],
    *,
    router: DataRouter,
    settings: Settings,
    registry: ProbeRegistry,
) -> list[dict[str, Any]]:
    if not specs:
        return []
    timeout = settings.readiness_timeout_seconds
    executor = ThreadPoolExecutor(max_workers=min(8, len(specs)), thread_name_prefix="pige360-readiness")
    futures: dict[Future[Any], tuple[CheckSpec, float]] = {}
    for spec in specs:
        override = registry.get(spec.name) or registry.get(spec.name.split(":", 1)[0])
        probe = override or spec.probe
        context = ProbeContext(spec.name, timeout, router, settings, spec.tenant)
        futures[executor.submit(probe, context)] = (spec, time.perf_counter())
    done, pending = wait(futures, timeout=timeout)
    results: list[dict[str, Any]] = []
    for future in done:
        spec, started = futures[future]
        try:
            state, details = _normalize_probe_result(future.result())
        except ProbeFailure as exc:
            state, details = "fail", {"code": exc.code}
        except Exception as exc:  # Mensagens de drivers podem conter DSNs/segredos.
            state, details = "fail", {"code": type(exc).__name__}
        results.append(
            {
                "name": spec.name,
                "status": state,
                "critical": spec.critical,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                **({"details": details} if details else {}),
            }
        )
    for future in pending:
        spec, started = futures[future]
        future.cancel()
        results.append(
            {
                "name": spec.name,
                "status": "fail",
                "critical": spec.critical,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                "details": {"code": "timeout"},
            }
        )
    executor.shutdown(wait=False, cancel_futures=True)
    return sorted(results, key=lambda item: item["name"])


def build_readiness_report(
    router: DataRouter,
    settings: Settings,
    *,
    probes: ProbeRegistry | None = None,
    plane: str = "platform",
) -> dict[str, Any]:
    """Executa readiness global sem retornar URLs, credenciais ou erros de driver."""
    registry = probes or {}
    production = settings.environment in {"production", "staging"}
    checks = _run_specs(
        [
            CheckSpec("control_database", True, _control_database),
            CheckSpec("control_migrations", True, _control_migrations),
            CheckSpec("tenant_catalog", True, _tenant_catalog),
        ],
        router=router,
        settings=settings,
        registry=registry,
    )

    tenants: list[dict[str, Any]] = []
    catalog = next((item for item in checks if item["name"] == "tenant_catalog"), None)
    if catalog and catalog["status"] == "pass":
        # O catálogo bruto viaja apenas entre probes; ``_public`` o remove do payload.
        raw_tenants = (catalog.get("details") or {}).get("_internal_tenants", [])
        tenants = [dict(item) for item in raw_tenants if isinstance(item, Mapping)]

    tenant_specs = [
        CheckSpec(f"tenant_database:{row['id']}", True, _tenant_database, tenant=row)
        for row in tenants
    ]
    storage_required = production or settings.readiness_require_object_storage
    storage_specs = [
        CheckSpec(f"tenant_storage:{row['id']}", storage_required, _tenant_storage, tenant=row)
        for row in tenants
    ]
    checks.extend(_run_specs(tenant_specs + storage_specs, router=router, settings=settings, registry=registry))

    dependency_specs = [
        CheckSpec("redis", production or settings.readiness_require_redis, _redis),
        CheckSpec("rabbitmq", production or settings.readiness_require_rabbitmq, _rabbitmq),
        CheckSpec("minio", storage_required, _minio),
    ]
    enabled_dependencies = [
        spec
        for spec in dependency_specs
        if spec.critical
        or (spec.name == "redis" and bool(settings.redis_url))
        or (spec.name == "rabbitmq" and bool(settings.rabbitmq_url))
        or (spec.name == "minio" and bool(settings.object_storage_endpoint))
    ]
    checks.extend(_run_specs(enabled_dependencies, router=router, settings=settings, registry=registry))

    failed_critical = [item["name"] for item in checks if item["critical"] and item["status"] != "pass"]
    public_checks: list[dict[str, Any]] = []
    for item in sorted(checks, key=lambda check: check["name"]):
        public = dict(item)
        if ":" in public["name"]:
            category, tenant_id = public["name"].split(":", 1)
            tenant = next((row for row in tenants if str(row.get("id")) == tenant_id), {})
            public["name"] = category
            public["tenant"] = {"id": tenant_id, "code": tenant.get("code")}
        public_checks.append(_public(public))
    ready = not failed_critical
    return {
        "status": "ready" if ready else "not_ready",
        "plane": plane,
        "environment": settings.environment,
        "checked_at": iso_now(),
        "summary": {
            "checks": len(public_checks),
            "passed": sum(1 for item in public_checks if item["status"] == "pass"),
            "failed": sum(1 for item in public_checks if item["status"] == "fail"),
            "active_tenants": len(tenants),
            "failed_critical": failed_critical,
        },
        "checks": public_checks,
    }
