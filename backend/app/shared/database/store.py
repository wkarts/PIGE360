from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Sequence


class SQLiteStore:
    """Adapter local determinístico. Produção usa o contrato PostgreSQL documentado."""

    def __init__(self, path: Path, schema_path: Path, extra_schema_paths: Sequence[Path] = ()):
        self.path = path
        self.schema_path = schema_path
        self.extra_schema_paths = tuple(extra_schema_paths)
        self._init_lock = threading.Lock()
        self._initialized = False

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=30, isolation_level=None, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        return conn

    def initialize(self) -> None:
        if self._initialized:
            return
        with self._init_lock:
            if self._initialized:
                return
            schemas = [self.schema_path, *self.extra_schema_paths]
            with self._connect() as conn:
                for path in schemas:
                    conn.executescript(path.read_text(encoding="utf-8"))
                self._apply_compatibility_migrations(conn)
            self._initialized = True

    @staticmethod
    def _apply_compatibility_migrations(conn: sqlite3.Connection) -> None:
        # Migrations locais pequenas e idempotentes para instalações SQLite de desenvolvimento
        # criadas antes de o schema físico atual existir. Produção usa Alembic/PostgreSQL.
        outbox = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='outbox_events'").fetchone()
        if outbox:
            outbox_columns = {row[1] for row in conn.execute("PRAGMA table_info(outbox_events)").fetchall()}
            for column in ("last_error", "next_attempt_at"):
                if column not in outbox_columns:
                    conn.execute(f"ALTER TABLE outbox_events ADD COLUMN {column} TEXT")
        fiscal_profiles = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='fiscal_profiles'").fetchone()
        if fiscal_profiles:
            columns = {row[1] for row in conn.execute("PRAGMA table_info(fiscal_profiles)").fetchall()}
            if "provider_connection_id" not in columns:
                conn.execute("ALTER TABLE fiscal_profiles ADD COLUMN provider_connection_id TEXT")
        fiscal_documents = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='fiscal_documents'").fetchone()
        if fiscal_documents:
            columns = {row[1] for row in conn.execute("PRAGMA table_info(fiscal_documents)").fetchall()}
            additions = {
                "provider_connection_id": "TEXT",
                "provider_document_id": "TEXT",
                "provider_status": "TEXT NOT NULL DEFAULT 'not_configured'",
                "attempts": "INTEGER NOT NULL DEFAULT 0",
                "last_attempt_at": "TEXT",
                "fiscal_context_id": "TEXT",
                "fiscal_context_version_id": "TEXT",
                "fiscal_context_snapshot_json": "TEXT NOT NULL DEFAULT '{}'",
                "delivery_policy_id": "TEXT",
                "retry_count": "INTEGER NOT NULL DEFAULT 0",
                "next_retry_at": "TEXT",
            }
            for column, ddl in additions.items():
                if column not in columns:
                    conn.execute(f"ALTER TABLE fiscal_documents ADD COLUMN {column} {ddl}")

        otp_table = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='signature_otp_challenges'").fetchone()
        if otp_table:
            columns = {row[1] for row in conn.execute("PRAGMA table_info(signature_otp_challenges)").fetchall()}
            additions = {
                "delivery_state": "TEXT NOT NULL DEFAULT 'queued'",
                "delivery_provider": "TEXT",
                "delivery_message_id": "TEXT",
                "delivery_error_code": "TEXT",
                "delivered_at": "TEXT",
            }
            for column, ddl in additions.items():
                if column not in columns:
                    conn.execute(f"ALTER TABLE signature_otp_challenges ADD COLUMN {column} {ddl}")

        # Compatibilidade do incremento vertical de serviços, compras, estoque e patrimônio.
        compatibility_columns = {
            "services": {
                "catalog_id": "TEXT", "service_type": "TEXT NOT NULL DEFAULT 'other'",
                "recurrence_type": "TEXT NOT NULL DEFAULT 'one_time'",
                "unit_of_measure": "TEXT NOT NULL DEFAULT 'unit'", "default_duration_minutes": "INTEGER",
                "cost_center_id": "TEXT", "taxable": "INTEGER NOT NULL DEFAULT 1",
                "metadata_json": "TEXT NOT NULL DEFAULT '{}'", "institution_id": "TEXT", "unit_id": "TEXT",
                "version": "INTEGER NOT NULL DEFAULT 1",
            },
            "service_orders": {
                "order_number": "TEXT", "subscriber_person_id": "TEXT", "subscription_id": "TEXT",
                "competence_id": "TEXT", "cost_center_id": "TEXT", "currency": "TEXT NOT NULL DEFAULT 'BRL'",
                "subtotal": "NUMERIC NOT NULL DEFAULT 0", "discount_amount": "NUMERIC NOT NULL DEFAULT 0",
                "due_date": "TEXT", "installment_count": "INTEGER NOT NULL DEFAULT 1", "charge_id": "TEXT",
                "fiscal_status": "TEXT NOT NULL DEFAULT 'pending'", "notes": "TEXT", "confirmed_at": "TEXT",
                "confirmed_by": "TEXT", "started_at": "TEXT", "completed_at": "TEXT", "cancelled_at": "TEXT",
                "cancellation_reason": "TEXT", "institution_id": "TEXT", "unit_id": "TEXT",
                "version": "INTEGER NOT NULL DEFAULT 1",
            },
            "service_order_items": {
                "variant_id": "TEXT", "description": "TEXT", "discount_amount": "NUMERIC NOT NULL DEFAULT 0",
                "competence_start": "TEXT", "competence_end": "TEXT",
                "fiscal_profile_snapshot_json": "TEXT NOT NULL DEFAULT '{}'",
                "execution_status": "TEXT NOT NULL DEFAULT 'pending'",
                "executed_quantity": "NUMERIC NOT NULL DEFAULT 0",
            },
            "stock_movements": {"lot_id": "TEXT", "balance_after": "NUMERIC"},
            "suppliers": {
                "code": "TEXT", "rating": "NUMERIC", "payment_terms_json": "TEXT NOT NULL DEFAULT '{}'",
                "fiscal_profile_json": "TEXT NOT NULL DEFAULT '{}'", "notes": "TEXT", "institution_id": "TEXT",
                "unit_id": "TEXT", "version": "INTEGER NOT NULL DEFAULT 1",
            },
            "purchase_orders": {
                "warehouse_id": "TEXT NOT NULL DEFAULT 'default'", "quotation_id": "TEXT", "requisition_id": "TEXT",
                "currency": "TEXT NOT NULL DEFAULT 'BRL'", "subtotal": "NUMERIC NOT NULL DEFAULT 0",
                "freight_amount": "NUMERIC NOT NULL DEFAULT 0", "discount_amount": "NUMERIC NOT NULL DEFAULT 0",
                "notes": "TEXT", "approved_at": "TEXT", "approved_by": "TEXT", "closed_at": "TEXT",
                "institution_id": "TEXT", "unit_id": "TEXT", "version": "INTEGER NOT NULL DEFAULT 1",
            },
            "purchase_order_items": {
                "returned_quantity": "NUMERIC NOT NULL DEFAULT 0", "discount_amount": "NUMERIC NOT NULL DEFAULT 0",
                "total_amount": "NUMERIC NOT NULL DEFAULT 0",
                "fiscal_profile_snapshot_json": "TEXT NOT NULL DEFAULT '{}'",
            },
            "inventory_counts": {
                "started_at": "TEXT", "snapshot_json": "TEXT NOT NULL DEFAULT '{}'", "institution_id": "TEXT",
                "unit_id": "TEXT", "version": "INTEGER NOT NULL DEFAULT 1",
            },
            "inventory_count_items": {"lot_id": "TEXT", "notes": "TEXT"},
            "assets": {
                "tag": "TEXT", "name": "TEXT", "location_id": "TEXT", "product_id": "TEXT",
                "receipt_item_id": "TEXT", "serial_number": "TEXT", "useful_life_months": "INTEGER",
                "residual_value": "NUMERIC NOT NULL DEFAULT 0",
                "accumulated_depreciation": "NUMERIC NOT NULL DEFAULT 0", "warranty_until": "TEXT",
                "metadata_json": "TEXT NOT NULL DEFAULT '{}'", "institution_id": "TEXT", "unit_id": "TEXT",
                "version": "INTEGER NOT NULL DEFAULT 1",
            },
        }
        for table_name, additions in compatibility_columns.items():
            exists = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,)
            ).fetchone()
            if not exists:
                continue
            columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}
            for column, ddl in additions.items():
                if column not in columns:
                    conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column} {ddl}")

        table = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='legal_contracts'").fetchone()
        if not table:
            return
        for table_name in ("legal_contracts", "contract_versions"):
            columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}
            for column in ("signed_document_sha256", "signed_document_storage_key", "signature_profile"):
                if column not in columns:
                    conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column} TEXT")

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        self.initialize()
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def fetch_one(self, sql: str, params: Sequence[Any] = ()) -> dict[str, Any] | None:
        self.initialize()
        with self._connect() as conn:
            row = conn.execute(sql, tuple(params)).fetchone()
            return dict(row) if row else None

    def fetch_all(self, sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
        self.initialize()
        with self._connect() as conn:
            return [dict(row) for row in conn.execute(sql, tuple(params)).fetchall()]

    def scalar(self, sql: str, params: Sequence[Any] = ()) -> Any:
        row = self.fetch_one(sql, params)
        return next(iter(row.values())) if row else None

    def execute(self, sql: str, params: Sequence[Any] = ()) -> int:
        with self.transaction() as conn:
            result = conn.execute(sql, tuple(params))
            return result.rowcount

    def dump_json(self, value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
