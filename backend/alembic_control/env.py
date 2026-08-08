from __future__ import annotations

import os
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy.engine import make_url

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)
target_metadata = None


def _secret(env_name: str, file_name: str) -> str:
    value = os.getenv(env_name, "")
    if value:
        return value
    path = os.getenv(file_name, "")
    return Path(path).read_text(encoding="utf-8").strip() if path and Path(path).is_file() else ""


def _runtime_url() -> str:
    raw = os.getenv("DATABASE_CONTROL_URL", config.get_main_option("sqlalchemy.url"))
    password = _secret("DATABASE_CONTROL_PASSWORD", "DATABASE_CONTROL_PASSWORD_FILE")
    if password:
        raw = make_url(raw).set(password=password).render_as_string(hide_password=False)
    return raw


def run_migrations_offline() -> None:
    context.configure(
        url=_runtime_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        transaction_per_migration=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    from sqlalchemy import create_engine, pool
    sync_url = make_url(_runtime_url()).set(drivername="postgresql+psycopg").render_as_string(hide_password=False)
    connectable = create_engine(sync_url, poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
