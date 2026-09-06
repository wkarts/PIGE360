from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from app.bootstrap.config import Settings
from app.shared.database.router import DataRouter


ELIGIBLE_STATUSES = frozenset({"active", "degraded", "suspended"})


def migrate_existing_tenants(
    router: DataRouter,
    *,
    ensure_resources: bool = False,
    apply_migrations: bool = True,
) -> dict[str, Any]:
    """Reconcile every operational tenant database before application startup.

    Provisioning records that never reached an operational state are reported but
    deliberately skipped: a half-created tenant must not block upgrades for every
    healthy institution. Missing credentials on an operational tenant fail closed.
    """

    rows = router.control.fetch_all(
        """SELECT id,code,status,database_name,database_user,database_secret_ciphertext
           FROM platform_tenants ORDER BY id"""
    )
    result: dict[str, Any] = {"discovered": len(rows), "migrated": [], "skipped": [], "errors": []}

    for row in rows:
        tenant_id = str(row.get("id") or "")
        code = str(row.get("code") or tenant_id)
        status = str(row.get("status") or "").lower()
        public_record = {"tenant_id": tenant_id, "code": code, "status": status}
        if status not in ELIGIBLE_STATUSES:
            result["skipped"].append({**public_record, "reason": "non_operational_status"})
            continue

        database_name = str(row.get("database_name") or "")
        database_user = str(row.get("database_user") or "")
        ciphertext = str(row.get("database_secret_ciphertext") or "")
        if not database_name or not database_user or not ciphertext:
            result["errors"].append({**public_record, "reason": "database_metadata_incomplete"})
            continue

        try:
            password = router._decrypt_secret(ciphertext)
            if ensure_resources:
                router._create_postgres_database(database_name, database_user, password)
            if apply_migrations:
                tenant_url = router._url_with_password(
                    router.settings.database_tenant_admin_url,
                    password,
                    username=database_user,
                    database=database_name,
                )
                router._upgrade_tenant_database(tenant_url)
            result["migrated"].append({**public_record, "database_name": database_name})
        except Exception as exc:  # pragma: no cover - exact driver errors depend on the host
            # Driver exceptions can embed a DSN. Never serialize their message because
            # it may contain the decrypted per-tenant password.
            result["errors"].append({**public_record, "reason": type(exc).__name__})

    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reconcilia bancos PostgreSQL dos tenants existentes.")
    parser.add_argument(
        "--ensure-resources",
        action="store_true",
        help="Cria/atualiza roles e cria bancos ausentes antes das migrations (uso em restore).",
    )
    parser.add_argument(
        "--skip-migrations",
        action="store_true",
        help="Somente garante roles/bancos; não executa Alembic tenant.",
    )
    args = parser.parse_args(argv)

    settings = Settings.from_env()
    router = DataRouter(settings)
    try:
        router.initialize()
        result = migrate_existing_tenants(
            router,
            ensure_resources=args.ensure_resources,
            apply_migrations=not args.skip_migrations,
        )
    finally:
        router.close()

    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    if result["errors"]:
        print("Falha ao reconciliar um ou mais bancos operacionais de tenant.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
