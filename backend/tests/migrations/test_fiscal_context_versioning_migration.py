from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CONFIG = ROOT / "backend" / "alembic_tenant" / "alembic.ini"
DATABASE_URL = "postgresql+asyncpg://pige360_tenant:local-only@localhost:5432/tenant_template"


def _alembic(*arguments: str) -> str:
    environment = os.environ.copy()
    environment["DATABASE_TENANT_URL"] = DATABASE_URL
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(CONFIG), *arguments, "--sql"],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout + result.stderr


def test_0032_upgrade_is_renderable_versioned_and_tenant_isolated() -> None:
    sql = _alembic(
        "upgrade",
        "0031_inventory_reorder_suggestions:0032_fiscal_context_versioning",
    )
    for table in (
        "fiscal_contexts",
        "fiscal_context_versions",
        "fiscal_context_operation_scopes",
    ):
        assert (
            f'CREATE TABLE "{table}"' in sql
            or f"CREATE TABLE {table}" in sql
            or f"CREATE TABLE IF NOT EXISTS {table}" in sql
        )
        assert f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY' in sql
        assert f"CREATE POLICY {table}_tenant_isolation" in sql
    assert "fiscal_context_snapshot_json" in sql
    assert "ck_fiscal_context_version_period" in sql
    assert "ix_fiscal_context_versions_effective" in sql
    assert "0032_fiscal_context_versioning" in sql


def test_0032_downgrade_removes_only_the_increment() -> None:
    sql = _alembic(
        "downgrade",
        "0032_fiscal_context_versioning:0031_inventory_reorder_suggestions",
    )
    for table in (
        "fiscal_context_operation_scopes",
        "fiscal_context_versions",
        "fiscal_contexts",
    ):
        assert f'DROP TABLE IF EXISTS "{table}"' in sql or f"DROP TABLE IF EXISTS {table}" in sql
    assert "DROP COLUMN IF EXISTS fiscal_context_snapshot_json" in sql
    assert "version_num='0031_inventory_reorder_suggestions'" in sql
    assert "0001_tenant" not in sql
