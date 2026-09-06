from __future__ import annotations

import asyncio
import json
import re
import threading
from contextlib import contextmanager
from decimal import Decimal
from typing import Any, Iterator, Sequence
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine


_QMARK = re.compile(r"\?")


def _normalize_value(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        return value
    return value


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, UUID):
            result[key] = str(value)
        elif isinstance(value, Decimal):
            result[key] = str(value)
        elif isinstance(value, (dict, list)):
            # O domínio atual trabalha com campos *_json serializados; a fronteira
            # preserva o mesmo contrato entre SQLite e PostgreSQL.
            result[key] = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        else:
            result[key] = value
    return result


def _compile(sql: str, params: Sequence[Any]) -> tuple[str, dict[str, Any]]:
    """Converte o contrato qmark usado pelos handlers para parâmetros SQLAlchemy.

    A função não concatena valores no SQL. Também traduz as poucas extensões SQLite
    usadas por fluxos idempotentes para equivalentes PostgreSQL.
    """
    values = list(params)
    # `tenant_id IS ?` é usado no serviço de autenticação para o Control Plane.
    out: list[str] = []
    bind: dict[str, Any] = {}
    idx = 0
    pos = 0
    for match in _QMARK.finditer(sql):
        prefix = sql[pos:match.start()]
        value = values[idx]
        idx += 1
        is_predicate = re.search(r"\bIS\s*$", prefix, flags=re.IGNORECASE)
        if is_predicate and value is None:
            out.append(prefix + "NULL")
        else:
            name = f"p{idx-1}"
            if is_predicate:
                # SQLite tolera `IS ?` para igualdade também; no PostgreSQL,
                # valores não nulos devem usar `=`. Mantemos `IS NULL` acima.
                prefix = re.sub(r"\bIS\s*$", "= ", prefix, flags=re.IGNORECASE)
            out.append(prefix + f":{name}")
            bind[name] = _normalize_value(value)
        pos = match.end()
    out.append(sql[pos:])
    compiled = "".join(out)
    if idx != len(values):
        raise ValueError(f"Quantidade de parâmetros incompatível: SQL consumiu {idx}, recebeu {len(values)}")
    # SQLite `INSERT OR IGNORE` -> PostgreSQL `ON CONFLICT DO NOTHING`.
    if re.match(r"\s*INSERT\s+OR\s+IGNORE\s+INTO\s+", compiled, flags=re.IGNORECASE):
        compiled = re.sub(r"INSERT\s+OR\s+IGNORE\s+INTO", "INSERT INTO", compiled, count=1, flags=re.IGNORECASE)
        compiled = compiled.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
    return compiled, bind


class _SyncResult:
    def __init__(self, rows: list[dict[str, Any]], rowcount: int = -1):
        self._rows = rows
        self.rowcount = rowcount

    def fetchone(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None

    def fetchall(self) -> list[dict[str, Any]]:
        return list(self._rows)


class _TransactionConnection:
    def __init__(self, store: "PostgresStore", connection: AsyncConnection):
        self._store = store
        self._connection = connection

    def execute(self, sql: str, params: Sequence[Any] = ()) -> _SyncResult:
        return self._store._run(self._execute(sql, params))

    async def _execute(self, sql: str, params: Sequence[Any]) -> _SyncResult:
        statement, bind = _compile(sql, params)
        result = await self._connection.execute(text(statement), bind)
        rows: list[dict[str, Any]] = []
        if result.returns_rows:
            rows = [_normalize_row(dict(row)) for row in result.mappings().all()]
        return _SyncResult(rows, result.rowcount)


class PostgresStore:
    """Facade síncrona sobre SQLAlchemy 2 AsyncEngine/asyncpg.

    Os endpoints FastAPI existentes são handlers síncronos executados no threadpool.
    Para manter o contrato transacional sem reescrever os domínios, cada store mantém
    um event-loop privado e todo I/O PostgreSQL ocorre no AsyncEngine. Uma futura
    migração de handlers para `async def` pode remover esta facade sem alterar SQL.
    """

    def __init__(self, url: str, *, tenant_id: str | None = None, pool_size: int = 10, max_overflow: int = 10):
        if not url.startswith("postgresql+asyncpg://"):
            raise ValueError("PostgresStore exige URL postgresql+asyncpg://")
        self.url = url
        self.tenant_id = tenant_id
        self._engine: AsyncEngine = create_async_engine(
            url,
            pool_pre_ping=True,
            pool_size=pool_size,
            max_overflow=max_overflow,
        )
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, name=f"pige360-pg-{tenant_id or 'control'}", daemon=True)
        self._thread.start()

    def initialize(self) -> None:
        self._run(self._healthcheck())

    async def _healthcheck(self) -> None:
        async with self._engine.connect() as conn:
            await conn.execute(text("SELECT 1"))

    def _run(self, coroutine):
        future = asyncio.run_coroutine_threadsafe(coroutine, self._loop)
        return future.result(timeout=60)

    async def _prepare(self, conn: AsyncConnection) -> None:
        if self.tenant_id:
            await conn.execute(text("SELECT set_config('app.tenant_id', :tenant_id, true)"), {"tenant_id": self.tenant_id})

    @contextmanager
    def transaction(self) -> Iterator[_TransactionConnection]:
        connection = self._run(self._engine.connect())
        transaction = self._run(connection.begin())
        try:
            self._run(self._prepare(connection))
            yield _TransactionConnection(self, connection)
            self._run(transaction.commit())
        except Exception:
            self._run(transaction.rollback())
            raise
        finally:
            self._run(connection.close())

    @staticmethod
    def transaction_lock(conn: _TransactionConnection, namespace: str) -> None:
        """Adquire lock transacional nomeado sem interpolar o namespace no SQL."""

        conn.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(?, 0))",
            (namespace,),
        )

    async def _fetch(self, sql: str, params: Sequence[Any], all_rows: bool) -> Any:
        statement, bind = _compile(sql, params)
        async with self._engine.connect() as conn:
            await self._prepare(conn)
            result = await conn.execute(text(statement), bind)
            mappings = result.mappings()
            if all_rows:
                return [_normalize_row(dict(row)) for row in mappings.all()]
            row = mappings.first()
            return _normalize_row(dict(row)) if row else None

    def fetch_one(self, sql: str, params: Sequence[Any] = ()) -> dict[str, Any] | None:
        return self._run(self._fetch(sql, params, False))

    def fetch_all(self, sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
        return self._run(self._fetch(sql, params, True))

    def scalar(self, sql: str, params: Sequence[Any] = ()) -> Any:
        row = self.fetch_one(sql, params)
        return next(iter(row.values())) if row else None

    def execute(self, sql: str, params: Sequence[Any] = ()) -> int:
        with self.transaction() as conn:
            return conn.execute(sql, params).rowcount

    def dump_json(self, value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    def close(self) -> None:
        try:
            self._run(self._engine.dispose())
        finally:
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join(timeout=5)
