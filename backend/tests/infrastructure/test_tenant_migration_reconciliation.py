from __future__ import annotations

from dataclasses import dataclass

from app.shared.database.migrate_tenants import migrate_existing_tenants


class _Control:
    def __init__(self, rows: list[dict[str, str | None]]):
        self.rows = rows

    def fetch_all(self, _sql: str):
        return self.rows


@dataclass
class _Settings:
    database_tenant_admin_url: str = "postgresql+asyncpg://admin@postgres/tenants"


class _Router:
    def __init__(self, rows: list[dict[str, str | None]]):
        self.control = _Control(rows)
        self.settings = _Settings()
        self.created: list[tuple[str, str, str]] = []
        self.upgraded: list[str] = []

    def _decrypt_secret(self, value: str) -> str:
        return f"plain-{value}"

    def _create_postgres_database(self, name: str, user: str, password: str) -> None:
        self.created.append((name, user, password))

    def _url_with_password(self, url: str, password: str, *, username: str, database: str) -> str:
        return f"{url}|{username}|{database}|{password}"

    def _upgrade_tenant_database(self, url: str) -> None:
        self.upgraded.append(url)


class _FailingRouter(_Router):
    def _upgrade_tenant_database(self, url: str) -> None:
        raise RuntimeError(f"driver failed with secret: {url}")


def _tenant(status: str = "active", *, ciphertext: str | None = "cipher") -> dict[str, str | None]:
    return {
        "id": "tenant-1",
        "code": "school",
        "status": status,
        "database_name": "pige360_t_1",
        "database_user": "pige360_u_1",
        "database_secret_ciphertext": ciphertext,
    }


def test_reconciles_operational_tenant_and_can_ensure_resources() -> None:
    router = _Router([_tenant()])

    result = migrate_existing_tenants(router, ensure_resources=True)

    assert not result["errors"]
    assert result["migrated"][0]["tenant_id"] == "tenant-1"
    assert router.created == [("pige360_t_1", "pige360_u_1", "plain-cipher")]
    assert router.upgraded == [
        "postgresql+asyncpg://admin@postgres/tenants|pige360_u_1|pige360_t_1|plain-cipher"
    ]


def test_skips_failed_provisioning_without_blocking_healthy_tenants() -> None:
    router = _Router([_tenant("failed"), {**_tenant(), "id": "tenant-2", "code": "healthy"}])

    result = migrate_existing_tenants(router)

    assert len(result["skipped"]) == 1
    assert result["skipped"][0]["reason"] == "non_operational_status"
    assert [item["tenant_id"] for item in result["migrated"]] == ["tenant-2"]


def test_fails_closed_when_operational_tenant_metadata_is_incomplete() -> None:
    router = _Router([_tenant(ciphertext=None)])

    result = migrate_existing_tenants(router)

    assert not result["migrated"]
    assert result["errors"][0]["reason"] == "database_metadata_incomplete"
    assert not router.upgraded


def test_driver_error_never_serializes_decrypted_credentials() -> None:
    router = _FailingRouter([_tenant("degraded")])

    result = migrate_existing_tenants(router)

    serialized = str(result)
    assert result["errors"][0]["reason"] == "RuntimeError"
    assert "plain-cipher" not in serialized
    assert "database_secret_ciphertext" not in serialized
