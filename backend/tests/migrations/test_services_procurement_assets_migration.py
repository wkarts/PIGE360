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


def test_0030_upgrade_is_renderable_and_enforces_tenant_boundaries() -> None:
    sql = _alembic(
        "upgrade",
        "0029_admissions_funnel:0030_services_procurement_assets_vertical",
    )
    for table in (
        "service_catalogs",
        "service_subscriptions",
        "purchase_requisitions",
        "requests_for_quotation",
        "goods_receipts",
        "inventory_lots",
        "inventory_reservations",
        "asset_locations",
        "asset_movements",
        "asset_depreciations",
    ):
        assert (
            f'CREATE TABLE \"{table}\"' in sql
            or f"CREATE TABLE {table}" in sql
            or f"CREATE TABLE IF NOT EXISTS {table}" in sql
        )
        assert f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY' in sql
        assert f'CREATE POLICY {table}_tenant_isolation' in sql
    assert "0030_services_procurement_assets_vertical" in sql
    assert "uq_assets_tag" in sql
    assert "uq_suppliers_code" in sql


def test_0030_downgrade_is_renderable_without_destroying_the_tenant_plane() -> None:
    sql = _alembic(
        "downgrade",
        "0030_services_procurement_assets_vertical:0029_admissions_funnel",
    )
    for table in (
        "service_catalogs",
        "purchase_requisitions",
        "goods_receipts",
        "inventory_lots",
        "asset_locations",
        "asset_depreciations",
    ):
        assert f'DROP TABLE IF EXISTS "{table}"' in sql or f"DROP TABLE IF EXISTS {table}" in sql
    assert "version_num='0029_admissions_funnel'" in sql
    assert "0001_tenant" not in sql
    assert "Downgrade destrutivo do Tenant Plane" not in sql
