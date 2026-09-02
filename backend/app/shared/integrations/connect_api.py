from __future__ import annotations

import time
import urllib.parse
from typing import Any

from app.shared.integrations import providers as provider_registry
from app.shared.integrations.providers import BaseProvider, IntegrationError, ProviderHealth


CONNECT_API_PROVIDER_ALIASES = frozenset(
    {
        "connect_api",
        "ConnectApiProvider",
        "ConnectAPIProvider",
        # Compatibilidade de leitura de configurações históricas. Estes nomes
        # nunca devem voltar a ser apresentados nas APIs/UX do PIGE360.
        "evolution",
        "EvolutionApiProvider",
    }
)


class ConnectApiProvider(BaseProvider):
    """Adapter canônico de comunicação do PIGE360 para Connect API.

    Mantém o contrato HTTP historicamente compatível para permitir migração sem
    interrupção, mas normaliza identidade, erros e telemetria para Connect API.
    O payload de mensagem segue o contrato Meta-compatible usado pela plataforma:
    número E.164 somente dígitos, texto e metadados opcionais de atraso/preview.
    """

    provider_name = "connect_api"

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self.base = self._https_base(self.config, "base_url")
        auth_header = str(self.config.get("auth_header") or "apikey").strip()
        if not auth_header:
            raise IntegrationError("CONNECT_API_AUTH_HEADER_INVALID", "Cabeçalho de autenticação da Connect API é inválido.")
        self.headers = {auth_header: self.secret}
        self.health_path = str(self.config.get("health_path") or "/instance/fetchInstances")
        self.send_text_path = str(self.config.get("send_text_path") or "/message/sendText/{instance}")
        if not self.health_path.startswith("/"):
            raise IntegrationError("CONNECT_API_HEALTH_PATH_INVALID", "health_path da Connect API deve iniciar com '/'.")
        if not self.send_text_path.startswith("/") or "{instance}" not in self.send_text_path:
            raise IntegrationError(
                "CONNECT_API_SEND_PATH_INVALID",
                "send_text_path da Connect API deve iniciar com '/' e conter '{instance}'.",
            )

    def health(self) -> ProviderHealth:
        started = time.perf_counter()
        status, payload = self.transport.request_json(
            "GET",
            f"{self.base}{self.health_path}",
            headers=self.headers,
            retries=2,
        )
        healthy = status == 200
        instances: int | None = None
        if isinstance(payload, list):
            instances = len(payload)
        elif isinstance(payload, dict):
            raw_instances = payload.get("instances") or payload.get("data")
            if isinstance(raw_instances, list):
                instances = len(raw_instances)
        return ProviderHealth(
            "healthy" if healthy else "degraded",
            self.provider_name,
            round((time.perf_counter() - started) * 1000),
            {
                "http_status": status,
                "instances": instances,
                "compatibility": "meta",
                "canonical_provider": "Connect API",
            },
        )

    def send_text(self, *, instance: str, number: str, text: str, delay_ms: int = 0) -> Any:
        normalized_instance = instance.strip()
        normalized_number = "".join(character for character in number if character.isdigit())
        if not normalized_instance or not normalized_number or len(normalized_number) < 8 or len(normalized_number) > 20 or not text:
            raise IntegrationError(
                "CONNECT_API_MESSAGE_INVALID",
                "instance, número E.164 e texto são obrigatórios para a Connect API.",
            )
        path = self.send_text_path.replace(
            "{instance}", urllib.parse.quote(normalized_instance, safe="")
        )
        body = {
            "number": normalized_number,
            "text": text,
            "delay": max(0, int(delay_ms)),
            "linkPreview": False,
        }
        status, payload = self.transport.request_json(
            "POST",
            f"{self.base}{path}",
            headers=self.headers,
            body=body,
            retries=0,
        )
        if status not in {200, 201, 202} or payload is None:
            raise IntegrationError(
                "CONNECT_API_SEND_FAILED",
                "Connect API não confirmou o envio da mensagem.",
                retryable=status >= 500,
                status=status,
            )
        return payload


def canonical_provider_name(provider: str) -> str:
    return "connect_api" if provider in CONNECT_API_PROVIDER_ALIASES else provider


def register_connect_api_provider() -> None:
    # Canonical writes usam `connect_api`. Aliases antigos continuam aceitos só
    # para leitura/execução de registros históricos existentes.
    for alias in CONNECT_API_PROVIDER_ALIASES:
        provider_registry.PROVIDERS[alias] = ConnectApiProvider


register_connect_api_provider()
