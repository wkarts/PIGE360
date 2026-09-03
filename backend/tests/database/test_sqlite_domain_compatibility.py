from __future__ import annotations

import sqlite3
from pathlib import Path

from app.shared.database.store import SQLiteStore


def _legacy_control_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE platform_tenants (
                id TEXT PRIMARY KEY,
                code TEXT NOT NULL UNIQUE,
                legal_name TEXT NOT NULL,
                trade_name TEXT NOT NULL,
                status TEXT NOT NULL,
                database_path TEXT NOT NULL UNIQUE,
                storage_path TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                version INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE tenant_domains (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL REFERENCES platform_tenants(id),
                hostname TEXT NOT NULL UNIQUE,
                surface TEXT NOT NULL DEFAULT 'admin',
                status TEXT NOT NULL,
                is_canonical INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );
            """
        )
        conn.execute(
            """INSERT INTO platform_tenants(
                id,code,legal_name,trade_name,status,database_path,storage_path,created_at,updated_at,version
            ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (
                "tenant-1",
                "escola-legada",
                "Escola Legada Ltda.",
                "Escola Legada",
                "active",
                "/legacy/tenant.db",
                "/legacy/storage",
                "2026-01-01T00:00:00Z",
                "2026-01-01T00:00:00Z",
                1,
            ),
        )
        conn.executemany(
            """INSERT INTO tenant_domains(id,tenant_id,hostname,surface,status,is_canonical,created_at)
               VALUES(?,?,?,?,?,?,?)""",
            [
                (
                    "domain-canonical",
                    "tenant-1",
                    "escola-legada.pige360.com.br",
                    "admin",
                    "active",
                    1,
                    "2026-01-01T00:00:00Z",
                ),
                (
                    "domain-custom",
                    "tenant-1",
                    "portal.escola-legada.example",
                    "public",
                    "active",
                    0,
                    "2026-01-02T00:00:00Z",
                ),
            ],
        )
        conn.commit()


def test_old_sqlite_control_domain_schema_is_upgraded_in_place(tmp_path: Path) -> None:
    db_path = tmp_path / "control.db"
    _legacy_control_db(db_path)
    schema_path = Path(__file__).resolve().parents[2] / "app/shared/database/control_schema.sql"

    SQLiteStore(db_path, schema_path).initialize()

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        columns = {row[1] for row in conn.execute("PRAGMA table_info(tenant_domains)").fetchall()}
        assert {
            "certificate_policy",
            "certificate_status",
            "verification_method",
            "verification_name",
            "verification_token",
            "verification_status",
            "provider",
            "provider_reference",
            "provider_validation_json",
            "verified_at",
            "activated_at",
            "last_error",
            "updated_at",
        } <= columns

        canonical = dict(conn.execute("SELECT * FROM tenant_domains WHERE id='domain-canonical'").fetchone())
        assert canonical["status"] == "active"
        assert canonical["certificate_policy"] == "canonical_wildcard"
        assert canonical["certificate_status"] == "active"
        assert canonical["verification_status"] == "not_required"
        assert canonical["provider"] == "platform_wildcard"
        assert canonical["provider_validation_json"] == "{}"
        assert canonical["activated_at"] == "2026-01-01T00:00:00Z"

        custom = dict(conn.execute("SELECT * FROM tenant_domains WHERE id='domain-custom'").fetchone())
        assert custom["status"] == "pending_verification"
        assert custom["certificate_policy"] == "edge_acme"
        assert custom["certificate_status"] == "not_requested"
        assert custom["verification_status"] == "pending"
        assert custom["provider"] is None
        assert custom["provider_validation_json"] == "{}"
        assert custom["activated_at"] is None
        assert "Revalidação obrigatória" in custom["last_error"]

    # Uma segunda inicialização representa restart/upgrade repetido e deve ser idempotente.
    SQLiteStore(db_path, schema_path).initialize()
    with sqlite3.connect(db_path) as conn:
        custom = conn.execute(
            "SELECT status,verification_status,last_error FROM tenant_domains WHERE id='domain-custom'"
        ).fetchone()
        assert custom[0] == "pending_verification"
        assert custom[1] == "pending"
        assert "Revalidação obrigatória" in custom[2]
