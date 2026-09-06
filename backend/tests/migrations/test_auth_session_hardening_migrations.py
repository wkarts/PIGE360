from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

import pytest

from app.shared.database.store import SQLiteStore


ROOT = Path(__file__).resolve().parents[2]


def _module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _sql(monkeypatch, module, action: str) -> str:
    statements: list[str] = []
    monkeypatch.setattr(module.op, "execute", lambda value: statements.append(str(value)))
    getattr(module, action)()
    return "\n".join(statements)


def test_control_migration_adds_login_limits_and_refresh_families(monkeypatch) -> None:
    module = _module(
        ROOT / "alembic_control/versions/0004_auth_session_hardening.py",
        "control_auth_hardening",
    )
    joined = _sql(monkeypatch, module, "upgrade")

    assert module.revision == "0004_auth_session_hardening"
    assert module.down_revision == "0003_custom_domains"
    assert "ADD COLUMN IF NOT EXISTS family_id" in joined
    assert "UPDATE refresh_tokens SET family_id=jti" in joined
    assert "CREATE TABLE IF NOT EXISTS auth_login_attempts" in joined
    assert "identifier_hash char(64) PRIMARY KEY" in joined


def test_control_rate_quota_migration_is_additive_and_persistent(monkeypatch) -> None:
    module = _module(
        ROOT / "alembic_control/versions/0005_tenant_api_rate_quota.py",
        "control_tenant_api_rate_quota",
    )
    joined = _sql(monkeypatch, module, "upgrade")

    assert module.revision == "0005_tenant_api_rate_quota"
    assert module.down_revision == "0004_auth_session_hardening"
    assert "CREATE TABLE IF NOT EXISTS tenant_api_rate_buckets" in joined
    assert "PRIMARY KEY (tenant_id, bucket_start)" in joined

    downgrade = _sql(monkeypatch, module, "downgrade")
    assert "DROP TABLE" not in downgrade


def test_tenant_migration_enforces_rls_for_login_limits(monkeypatch) -> None:
    module = _module(
        ROOT / "alembic_tenant/versions/0045_auth_session_hardening.py",
        "tenant_auth_hardening",
    )
    joined = _sql(monkeypatch, module, "upgrade")

    assert module.revision == "0045_auth_session_hardening"
    assert module.down_revision == "0044_school_sales_catalog_categories"
    assert "ADD COLUMN IF NOT EXISTS family_id" in joined
    assert "CREATE TABLE IF NOT EXISTS auth_login_attempts" in joined
    assert "ENABLE ROW LEVEL SECURITY" in joined
    assert "FORCE ROW LEVEL SECURITY" in joined
    assert "pige360_tenant_auth_login_attempts" in joined
    assert "current_setting('app.tenant_id', true)" in joined


def test_auth_hardening_downgrades_preserve_security_state(monkeypatch) -> None:
    modules = (
        _module(
            ROOT / "alembic_control/versions/0004_auth_session_hardening.py",
            "control_auth_hardening_downgrade",
        ),
        _module(
            ROOT / "alembic_tenant/versions/0045_auth_session_hardening.py",
            "tenant_auth_hardening_downgrade",
        ),
    )
    for module in modules:
        joined = _sql(monkeypatch, module, "downgrade")
        assert "DROP TABLE" not in joined
        assert "DROP COLUMN" not in joined


@pytest.mark.parametrize(
    ("schema_name", "tenant_id"),
    (("control_schema.sql", None), ("tenant_schema.sql", "tenant-legacy")),
)
def test_sqlite_legacy_refresh_rows_receive_session_family(
    tmp_path: Path,
    schema_name: str,
    tenant_id: str | None,
) -> None:
    database = tmp_path / f"{schema_name}.db"
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE refresh_tokens (
                jti TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                tenant_id TEXT,
                token_hash TEXT NOT NULL UNIQUE,
                expires_at TEXT NOT NULL,
                revoked_at TEXT,
                replaced_by TEXT,
                created_at TEXT NOT NULL
            );
            """
        )
        connection.execute(
            """INSERT INTO refresh_tokens(
                   jti,user_id,tenant_id,token_hash,expires_at,created_at
               ) VALUES(?,?,?,?,?,?)""",
            (
                "legacy-jti",
                "legacy-user",
                tenant_id,
                "legacy-hash",
                "2099-01-01T00:00:00+00:00",
                "2026-01-01T00:00:00+00:00",
            ),
        )

    store = SQLiteStore(database, ROOT / "app/shared/database" / schema_name)
    store.initialize()

    migrated = store.fetch_one("SELECT family_id FROM refresh_tokens WHERE jti=?", ("legacy-jti",))
    assert migrated == {"family_id": "legacy-jti"}
    assert store.fetch_one(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='auth_login_attempts'"
    ) == {"name": "auth_login_attempts"}
