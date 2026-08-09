from __future__ import annotations

import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.engine import make_url

from app.bootstrap.config import Settings
from app.shared.database.postgres_store import PostgresStore
from app.shared.database.store import SQLiteStore
from app.shared.domain.ids import iso_now, uuid7
from app.shared.presentation.errors import DomainError
from app.shared.storage.object_storage import LocalObjectStorage, S3ObjectStorage


@dataclass(frozen=True, slots=True)
class HostResolution:
    plane: str
    hostname: str
    tenant_id: str | None = None
    tenant_code: str | None = None
    surface: str | None = None


class DataRouter:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._production = settings.environment in {"production", "staging"}
        base = Path(__file__).parent
        self._tenant_schema = base / "tenant_schema.sql"
        self._operational_schema = base / "operational_schema.sql"
        self._tenant_stores: dict[str, SQLiteStore | PostgresStore] = {}
        self._object_stores: dict[str, LocalObjectStorage | S3ObjectStorage] = {}
        if self._production:
            control_url = self._url_with_password(settings.database_control_url, settings.database_control_password)
            self.control: SQLiteStore | PostgresStore = PostgresStore(
                control_url,
                pool_size=settings.database_pool_size,
                max_overflow=settings.database_max_overflow,
            )
            try:
                self._fernet = Fernet(settings.database_secret_key.encode("ascii"))
            except Exception as exc:
                raise RuntimeError("DATABASE_SECRET_KEY deve ser uma chave Fernet válida.") from exc
        else:
            self.control = SQLiteStore(settings.control_db_path, base / "control_schema.sql")
            self._fernet = None

    @staticmethod
    def _url_with_password(url: str, password: str, *, username: str | None = None, database: str | None = None) -> str:
        parsed = make_url(url)
        parsed = parsed.set(
            username=username if username is not None else parsed.username,
            password=password,
            database=database if database is not None else parsed.database,
        )
        return parsed.render_as_string(hide_password=False)

    def initialize(self) -> None:
        if not self._production:
            self.settings.data_root.mkdir(parents=True, exist_ok=True)
            self.settings.storage_root.mkdir(parents=True, exist_ok=True)
        self.control.initialize()

    def close(self) -> None:
        for store in list(self._tenant_stores.values()):
            if isinstance(store, PostgresStore):
                store.close()
        self._tenant_stores.clear()
        self._object_stores.clear()
        if isinstance(self.control, PostgresStore):
            self.control.close()

    def resolve_host(self, hostname: str) -> HostResolution:
        host = hostname.strip().lower().rstrip(".")
        if not host:
            raise DomainError("HOST_REQUIRED", "O cabeçalho Host é obrigatório.", 400)
        if host in self.settings.platform_hosts:
            return HostResolution(plane="platform", hostname=host)
        row = self.control.fetch_one(
            """SELECT d.tenant_id, d.surface, d.status, t.code, t.status AS tenant_status
               FROM tenant_domains d JOIN platform_tenants t ON t.id=d.tenant_id
               WHERE d.hostname=?""",
            (host,),
        )
        if not row:
            raise DomainError("UNKNOWN_HOST", "Domínio não associado a uma instituição.", 404, "Domínio desconhecido")
        if row["status"] != "active" or row["tenant_status"] != "active":
            raise DomainError("TENANT_UNAVAILABLE", "A instituição não está ativa.", 503)
        return HostResolution("tenant", host, row["tenant_id"], row["code"], row["surface"])

    def tenant_store(self, tenant_id: str) -> SQLiteStore | PostgresStore:
        cached = self._tenant_stores.get(tenant_id)
        if cached:
            return cached
        if self._production:
            row = self.control.fetch_one(
                "SELECT database_name,database_user,database_secret_ciphertext FROM platform_tenants WHERE id=?",
                (tenant_id,),
            )
            if not row or not row.get("database_name") or not row.get("database_user") or not row.get("database_secret_ciphertext"):
                raise DomainError("TENANT_DATABASE_NOT_READY", "Banco PostgreSQL do tenant não está provisionado.", 503)
            password = self._decrypt_secret(str(row["database_secret_ciphertext"]))
            url = self._url_with_password(
                self.settings.database_tenant_admin_url,
                password,
                username=str(row["database_user"]),
                database=str(row["database_name"]),
            )
            store = PostgresStore(
                url,
                tenant_id=tenant_id,
                pool_size=self.settings.database_pool_size,
                max_overflow=self.settings.database_max_overflow,
            )
        else:
            row = self.control.fetch_one("SELECT database_path FROM platform_tenants WHERE id=?", (tenant_id,))
            if not row:
                raise DomainError("TENANT_NOT_FOUND", "Tenant não localizado.", 404)
            store = SQLiteStore(Path(row["database_path"]), self._tenant_schema, (self._operational_schema,))
        store.initialize()
        self._tenant_stores[tenant_id] = store
        return store

    def provision_tenant(self, *, code: str, legal_name: str, trade_name: str, hostname: str) -> dict[str, Any]:
        existing = self.control.fetch_one("SELECT * FROM platform_tenants WHERE code=?", (code,))
        if existing:
            return existing
        if self._production:
            return self._provision_postgres_tenant(code=code, legal_name=legal_name, trade_name=trade_name, hostname=hostname)
        return self._provision_sqlite_tenant(code=code, legal_name=legal_name, trade_name=trade_name, hostname=hostname)

    def _provision_sqlite_tenant(self, *, code: str, legal_name: str, trade_name: str, hostname: str) -> dict[str, Any]:
        tenant_id = uuid7()
        tenant_root = self.settings.storage_root / tenant_id
        db_path = tenant_root / "database" / "tenant.db"
        storage_path = tenant_root / "storage"
        self._ensure_local_storage(storage_path)
        now = iso_now()
        with self.control.transaction() as conn:
            conn.execute(
                "INSERT INTO platform_tenants(id,code,legal_name,trade_name,status,database_path,storage_path,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (tenant_id, code, legal_name, trade_name, "active", str(db_path), str(storage_path), now, now),
            )
            conn.execute(
                "INSERT INTO tenant_domains(id,tenant_id,hostname,surface,status,is_canonical,created_at) VALUES(?,?,?,?,?,?,?)",
                (uuid7(), tenant_id, hostname.lower(), "admin", "active", 1, now),
            )
        store = self.tenant_store(tenant_id)
        with store.transaction() as conn:
            conn.execute("INSERT OR REPLACE INTO tenant_metadata(key,value) VALUES('tenant_id',?)", (tenant_id,))
            conn.execute("INSERT OR REPLACE INTO tenant_metadata(key,value) VALUES('tenant_code',?)", (code,))
        return self.control.fetch_one("SELECT * FROM platform_tenants WHERE id=?", (tenant_id,)) or {}

    def _provision_postgres_tenant(self, *, code: str, legal_name: str, trade_name: str, hostname: str) -> dict[str, Any]:
        tenant_id = uuid7()
        compact = tenant_id.replace("-", "")[:24]
        database_name = f"pige360_t_{compact}"
        database_user = f"pige360_u_{compact}"
        database_password = secrets.token_urlsafe(48)
        encrypted_password = self._encrypt_secret(database_password)
        bucket_name = f"pige360-tenant-{compact}"[:63]
        storage_path = f"/var/lib/pige360/tenants/{tenant_id}/storage"
        now = iso_now()

        with self.control.transaction() as conn:
            conn.execute(
                """INSERT INTO platform_tenants(
                       id,code,legal_name,trade_name,status,database_path,storage_path,database_name,database_user,
                       database_secret_ciphertext,bucket_name,storage_prefix,encryption_key_reference,created_at,updated_at
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    tenant_id, code, legal_name, trade_name, "provisioning", None, storage_path, database_name,
                    database_user, encrypted_password, bucket_name, tenant_id, f"tenant:{tenant_id}", now, now,
                ),
            )
            conn.execute(
                "INSERT INTO tenant_domains(id,tenant_id,hostname,surface,status,is_canonical,created_at) VALUES(?,?,?,?,?,?,?)",
                (uuid7(), tenant_id, hostname.lower(), "admin", "provisioning", 1, now),
            )

        try:
            self._create_postgres_database(database_name, database_user, database_password)
            object_store = S3ObjectStorage(
                endpoint_url=self.settings.object_storage_endpoint,
                access_key=self.settings.object_storage_access_key,
                secret_key=self.settings.object_storage_secret_key,
                bucket=bucket_name,
                region=self.settings.object_storage_region,
            )
            object_store.ensure_bucket()
            self._object_stores[tenant_id] = object_store
            tenant_url = self._url_with_password(
                self.settings.database_tenant_admin_url,
                database_password,
                username=database_user,
                database=database_name,
            )
            self._upgrade_tenant_database(tenant_url)
            store = PostgresStore(
                tenant_url,
                tenant_id=tenant_id,
                pool_size=self.settings.database_pool_size,
                max_overflow=self.settings.database_max_overflow,
            )
            store.initialize()
            with store.transaction() as conn:
                conn.execute(
                    "INSERT INTO tenant_metadata(key,value) VALUES('tenant_id',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (tenant_id,),
                )
                conn.execute(
                    "INSERT INTO tenant_metadata(key,value) VALUES('tenant_code',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (code,),
                )
            self._tenant_stores[tenant_id] = store
            with self.control.transaction() as conn:
                conn.execute("UPDATE platform_tenants SET status='active',updated_at=? WHERE id=?", (iso_now(), tenant_id))
                conn.execute("UPDATE tenant_domains SET status='active',updated_at=? WHERE tenant_id=?", (iso_now(), tenant_id))
        except Exception:
            with self.control.transaction() as conn:
                conn.execute("UPDATE platform_tenants SET status='failed',updated_at=? WHERE id=?", (iso_now(), tenant_id))
                conn.execute("UPDATE tenant_domains SET status='failed',updated_at=? WHERE tenant_id=?", (iso_now(), tenant_id))
            raise
        return self.control.fetch_one("SELECT * FROM platform_tenants WHERE id=?", (tenant_id,)) or {}

    def _create_postgres_database(self, database_name: str, database_user: str, database_password: str) -> None:
        try:
            import psycopg
            from psycopg import sql
        except ImportError as exc:
            raise RuntimeError("psycopg é obrigatório para provisionar bancos PostgreSQL de tenants.") from exc
        admin_url = self._url_with_password(
            self.settings.database_tenant_admin_url,
            self.settings.database_tenant_admin_password,
        )
        admin_url = make_url(admin_url).set(drivername="postgresql").render_as_string(hide_password=False)
        with psycopg.connect(admin_url, autocommit=True) as conn:
            role = conn.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (database_user,)).fetchone()
            if not role:
                conn.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD %s").format(sql.Identifier(database_user)), (database_password,))
            else:
                conn.execute(sql.SQL("ALTER ROLE {} LOGIN PASSWORD %s").format(sql.Identifier(database_user)), (database_password,))
            db = conn.execute("SELECT 1 FROM pg_database WHERE datname=%s", (database_name,)).fetchone()
            if not db:
                conn.execute(sql.SQL("CREATE DATABASE {} OWNER {}").format(sql.Identifier(database_name), sql.Identifier(database_user)))

    def _upgrade_tenant_database(self, tenant_url: str) -> None:
        backend_root = Path(__file__).resolve().parents[3]
        cfg = Config(str(backend_root / "alembic_tenant" / "alembic.ini"))
        cfg.set_main_option("script_location", str(backend_root / "alembic_tenant"))
        cfg.set_main_option("sqlalchemy.url", tenant_url)
        command.upgrade(cfg, "head")

    def _encrypt_secret(self, value: str) -> str:
        if not self._fernet:
            raise RuntimeError("Cifragem de credenciais indisponível fora do modo PostgreSQL.")
        return self._fernet.encrypt(value.encode("utf-8")).decode("ascii")

    def _decrypt_secret(self, value: str) -> str:
        if not self._fernet:
            raise RuntimeError("Cifragem de credenciais indisponível.")
        try:
            return self._fernet.decrypt(value.encode("ascii")).decode("utf-8")
        except InvalidToken as exc:
            raise RuntimeError("Credencial do banco do tenant não pôde ser decifrada.") from exc

    @staticmethod
    def _ensure_local_storage(storage_path: Path) -> None:
        for folder in [
            "documents", "academic", "finance", "fiscal", "sales", "canteen", "hr", "payroll",
            "timekeeping", "events", "mail-cache", "imports", "exports", "temporary", "quarantine",
            "backups", "audit", "branding", "app-factory", "contracts",
        ]:
            (storage_path / folder).mkdir(parents=True, exist_ok=True)


    def object_storage(self, tenant_id: str) -> LocalObjectStorage | S3ObjectStorage:
        cached = self._object_stores.get(tenant_id)
        if cached:
            return cached
        if self._production:
            row = self.control.fetch_one("SELECT bucket_name FROM platform_tenants WHERE id=?", (tenant_id,))
            if not row or not row.get("bucket_name"):
                raise DomainError("TENANT_STORAGE_NOT_READY", "Bucket S3/MinIO do tenant não está provisionado.", 503)
            storage = S3ObjectStorage(
                endpoint_url=self.settings.object_storage_endpoint,
                access_key=self.settings.object_storage_access_key,
                secret_key=self.settings.object_storage_secret_key,
                bucket=str(row["bucket_name"]),
                region=self.settings.object_storage_region,
            )
        else:
            storage = LocalObjectStorage(self.tenant_storage_path(tenant_id))
        self._object_stores[tenant_id] = storage
        return storage

    def tenant_storage_path(self, tenant_id: str) -> Path:
        row = self.control.fetch_one("SELECT storage_path FROM platform_tenants WHERE id=?", (tenant_id,))
        if not row:
            raise DomainError("TENANT_NOT_FOUND", "Tenant não localizado.", 404)
        return Path(row["storage_path"])
