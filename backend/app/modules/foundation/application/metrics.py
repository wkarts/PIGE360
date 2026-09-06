from __future__ import annotations

import threading
import time
from collections import defaultdict

from starlette.types import ASGIApp, Message, Receive, Scope, Send


PROMETHEUS_CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"
_KNOWN_HTTP_METHODS = frozenset({"CONNECT", "DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT", "TRACE"})


def _escape_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


class MetricsRegistry:
    """Registro Prometheus mínimo, local ao processo e sem dependência externa.

    Os labels são deliberadamente limitados a método e status. Caminho, hostname,
    tenant e correlation ID não entram nas séries para evitar cardinalidade alta e
    exposição acidental de dados operacionais.
    """

    def __init__(self, *, environment: str, version: str) -> None:
        self.environment = environment
        self.version = version
        self.started_at = time.time()
        self._started_monotonic = time.monotonic()
        self._lock = threading.Lock()
        self._requests: dict[tuple[str, int], int] = defaultdict(int)
        self._duration_count: dict[str, int] = defaultdict(int)
        self._duration_sum: dict[str, float] = defaultdict(float)

    @staticmethod
    def _method(value: str) -> str:
        normalized = value.upper()
        return normalized if normalized in _KNOWN_HTTP_METHODS else "OTHER"

    @staticmethod
    def _status(value: int) -> int:
        return value if 100 <= value <= 599 else 0

    def observe_http(self, *, method: str, status_code: int, duration_seconds: float) -> None:
        normalized_method = self._method(method)
        normalized_status = self._status(status_code)
        with self._lock:
            self._requests[(normalized_method, normalized_status)] += 1
            self._duration_count[normalized_method] += 1
            self._duration_sum[normalized_method] += max(0.0, duration_seconds)

    def render(self) -> str:
        with self._lock:
            requests = dict(self._requests)
            duration_count = dict(self._duration_count)
            duration_sum = dict(self._duration_sum)

        environment = _escape_label(self.environment)
        version = _escape_label(self.version)
        lines = [
            "# HELP pige360_build_info Informacao da instancia PIGE360 em execucao.",
            "# TYPE pige360_build_info gauge",
            f'pige360_build_info{{environment="{environment}",version="{version}"}} 1',
            "# HELP pige360_process_start_time_seconds Unix timestamp de inicio do processo.",
            "# TYPE pige360_process_start_time_seconds gauge",
            f"pige360_process_start_time_seconds {self.started_at:.6f}",
            "# HELP pige360_process_uptime_seconds Tempo de atividade do processo em segundos.",
            "# TYPE pige360_process_uptime_seconds gauge",
            f"pige360_process_uptime_seconds {max(0.0, time.monotonic() - self._started_monotonic):.6f}",
            "# HELP pige360_http_requests_total Total de requisicoes HTTP concluídas por metodo e status.",
            "# TYPE pige360_http_requests_total counter",
        ]
        for (method, status_code), count in sorted(requests.items()):
            lines.append(
                f'pige360_http_requests_total{{method="{method}",status_code="{status_code}"}} {count}'
            )
        lines.extend(
            [
                "# HELP pige360_http_request_duration_seconds Duracao acumulada das requisicoes HTTP por metodo.",
                "# TYPE pige360_http_request_duration_seconds summary",
            ]
        )
        for method in sorted(duration_count):
            lines.append(
                f'pige360_http_request_duration_seconds_count{{method="{method}"}} {duration_count[method]}'
            )
            lines.append(
                f'pige360_http_request_duration_seconds_sum{{method="{method}"}} {duration_sum[method]:.9f}'
            )
        return "\n".join(lines) + "\n"


class HttpMetricsMiddleware:
    """Observa toda resposta HTTP, inclusive rejeições antes da resolução de rota."""

    def __init__(self, app: ASGIApp, *, registry: MetricsRegistry) -> None:
        self.app = app
        self.registry = registry

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = time.perf_counter()
        status_code = 500

        async def send_with_status(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
            await send(message)

        try:
            await self.app(scope, receive, send_with_status)
        except BaseException:
            self.registry.observe_http(
                method=str(scope.get("method") or "OTHER"),
                status_code=500,
                duration_seconds=time.perf_counter() - started,
            )
            raise
        else:
            self.registry.observe_http(
                method=str(scope.get("method") or "OTHER"),
                status_code=status_code,
                duration_seconds=time.perf_counter() - started,
            )
