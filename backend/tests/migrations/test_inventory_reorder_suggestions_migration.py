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


def test_0031_upgrade_is_renderable_and_enforces_tenant_boundaries() -> None:
    sql = _alembic(
        "upgrade",
        "0030_services_procurement_assets_vertical:0031_inventory_reorder_suggestions",
    )
    for table in ("inventory_reorder_policies", "purchase_suggestions"):
        assert (
            f'CREATE TABLE "{table}"' in sql
            or f"CREATE TABLE {table}" in sql
            or f"CREATE TABLE IF NOT EXISTS {table}" in sql
        )
        assert f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY' in sql
        assert f'CREATE POLICY {table}_tenant_isolation' in sql
    assert "uq_purchase_suggestions_open_policy" in sql
    assert "0031_inventory_reorder_suggestions" in sql


def test_0031_downgrade_is_renderable_and_scoped_to_increment() -> None:
    sql = _alembic(
        "downgrade",
        "0031_inventory_reorder_suggestions:0030_services_procurement_assets_vertical",
    )
    for table in ("purchase_suggestions", "inventory_reorder_policies"):
        assert f'DROP TABLE IF EXISTS "{table}"' in sql or f"DROP TABLE IF EXISTS {table}" in sql
    assert "version_num='0030_services_procurement_assets_vertical'" in sql
    assert "0001_tenant" not in sql
