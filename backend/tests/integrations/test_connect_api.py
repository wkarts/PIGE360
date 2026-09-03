from __future__ import annotations

from pathlib import Path
from typing import Any

from app.bootstrap.config import Settings
from app.main import create_app
from app.shared.integrations.connect_api import ConnectApiProvider
from app.shared.integrations.providers import build_provider


class FakeTransport:
    def __init__(self):
        self.calls: list[dict[str, Any]] = []

    def request_json(self, method: str, url: str, *, headers: dict[str, str], body: Any | None = None, timeout: float = 20.0, retries: int = 2):
        self.calls.append({"method": method, "url": url, "headers": headers, "body": body, "retries": retries})
        if method == "GET":
            return 200, [{"instanceName": "school-main"}]
        return 201, {"key": {"id": "message-001"}}


def _provider(alias: str = "connect_api") -> tuple[ConnectApiProvider, FakeTransport]:
    transport = FakeTransport()
    provider = build_provider(
        alias,
        config={"base_url": "https://connect.example.com"},
        secret="test-api-key",
        transport=transport,
    )
    assert isinstance(provider, ConnectApiProvider)
    return provider, transport


def test_connect_api_is_canonical_provider_and_meta_compatible():
    provider, transport = _provider()

    health = provider.health()
    result = provider.send_text(
        instance="school-main",
        number="5575988881111",
        text="Mensagem PIGE360",
        delay_ms=250,
    )

    assert provider.provider_name == "connect_api"
    assert health.status == "healthy"
    assert health.details["compatibility"] == "meta"
    assert health.details["canonical_provider"] == "Connect API"
    assert result["key"]["id"] == "message-001"
    assert transport.calls[-1]["url"].endswith("/message/sendText/school-main")
    assert transport.calls[-1]["body"]["number"] == "5575988881111"


def test_legacy_provider_alias_executes_through_connect_api_adapter():
    # Compatibilidade de persistência: registros históricos são lidos pelo novo
    # adapter e podem ser migrados sem indisponibilidade.
    provider, _ = _provider("evolution")
    assert provider.provider_name == "connect_api"


def test_openapi_exposes_connect_api_and_hides_legacy_http_surface(tmp_path: Path):
    app = create_app(Settings().testing(tmp_path / "runtime"))
    paths = app.openapi()["paths"]

    assert "/api/v1/integration-connections/{connection_id}/connect-api/messages/text" in paths
    assert "/api/v1/integration-connections/{connection_id}/connect-api/migrate" in paths
    assert not any("/evolution/" in path.lower() for path in paths)

    operation_ids = {
        operation.get("operationId")
        for path in paths.values()
        for operation in path.values()
        if isinstance(operation, dict)
    }
    assert "connect_api_send_text" in operation_ids
    assert "evolution_send_text" not in operation_ids
