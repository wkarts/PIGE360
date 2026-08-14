from __future__ import annotations

import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
PYPROJECT = ROOT / "backend" / "pyproject.toml"
PRODUCTION_LOCK = ROOT / "backend" / "requirements.production.lock"


def _pins() -> set[str]:
    return {
        line.strip()
        for line in PRODUCTION_LOCK.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def test_production_lock_uses_a_published_psycopg_binary_release() -> None:
    dependencies = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]["optional-dependencies"]["production"]

    assert "psycopg[binary]==3.2.13" in _pins()
    assert "psycopg[binary]==3.2.0" not in _pins()
    assert "psycopg[binary]>=3.2.2,<4" in dependencies
