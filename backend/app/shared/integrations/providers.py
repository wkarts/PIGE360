from __future__ import annotations

import ipaddress
import json
import re
import socket
import smtplib
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Protocol


class IntegrationError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool = False, status: int | None = None):
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.status = status


class SecretResolver:
    """Resolve referências lógicas sem permitir path traversal ou paths arbitrários."""

    _NAME = re.compile(r"^[A-Za-z0-9_.-]{1,120}$")

    def __init__(self, root: Path):
        self.root = root.resolve()

    def resolve(self, reference: str | None) -> str:
        if not reference:
            raise IntegrationError("INTEGRATION_SECRET_NOT_CONFIGURED", "Credencial da integração não configurada.")
        if not self._NAME.fullmatch(reference):
            raise IntegrationError("INTEGRATION_SECRET_REFERENCE_INVALID", "Referência de segredo inválida.")
        for name in (reference, f"{reference}.txt"):
            candidate = (self.root / name).resolve()
            if candidate.parent != self.root:
                raise IntegrationError("INTEGRATION_SECRET_REFERENCE_INVALID", "Referência de segredo fora do diretório permitido.")
            if candidate.is_file():
                value = candidate.read_text(encoding="utf-8").strip()
                if value:
                    return value
        raise IntegrationError("INTEGRATION_SECRET_NOT_FOUND", "Segredo referenciado não está disponível neste runtime.")


class Transport(Protocol):
    def request_json(self, method: str, url: str, *, headers: dict[str, str], body: Any | None = None, timeout: float = 20.0, retries: int = 2) -> tuple[int, Any]: ...
    def request_form(self, method: str, url: str, *, headers: dict[str, str], form: dict[str, str], timeout: float = 20.0, retries: int = 0) -> tuple[int, Any]: ...
    def request_bytes(self, method: str, url: str, *, headers: dict[str, str], timeout: float = 30.0, retries: int = 2) -> tuple[int, bytes]: ...


class DisabledTransport:
    """Bloqueia qualquer I/O externo em testes/builds locais offline."""

    @staticmethod
    def _blocked() -> None:
        raise IntegrationError(
            "INTEGRATION_REMOTE_DISABLED",
            "Operações externas estão desabilitadas neste runtime.",
            retryable=False,
        )

    def request_json(self, method: str, url: str, *, headers: dict[str, str], body: Any | None = None, timeout: float = 20.0, retries: int = 2) -> tuple[int, Any]:
        self._blocked()

    def request_form(self, method: str, url: str, *, headers: dict[str, str], form: dict[str, str], timeout: float = 20.0, retries: int = 0) -> tuple[int, Any]:
        self._blocked()

    def request_bytes(self, method: str, url: str, *, headers: dict[str, str], timeout: float = 30.0, retries: int = 2) -> tuple[int, bytes]:
        self._blocked()


def _validate_outbound_url(url: str, *, allow_private_network: bool) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise IntegrationError("INTEGRATION_URL_INVALID", "A URL externa deve usar HTTPS e não pode conter credenciais.")
    host = parsed.hostname.rstrip(".").lower()
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".localhost"):
        if not allow_private_network:
            raise IntegrationError("INTEGRATION_SSRF_BLOCKED", "Destino local bloqueado pela política de SSRF.")
        return
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None and (literal.is_private or literal.is_loopback or literal.is_link_local or literal.is_multicast or literal.is_reserved or literal.is_unspecified):
        if not allow_private_network:
            raise IntegrationError("INTEGRATION_SSRF_BLOCKED", "Endereço privado/reservado bloqueado pela política de SSRF.")


class UrlLibTransport:
    def __init__(self, *, allow_private_network: bool = False):
        self.allow_private_network = allow_private_network

    def _validate_dns(self, url: str) -> None:
        _validate_outbound_url(url, allow_private_network=self.allow_private_network)
        if self.allow_private_network:
            return
        host = urllib.parse.urlparse(url).hostname
        if not host:
            return
        try:
            infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise IntegrationError("INTEGRATION_DNS_ERROR", "Não foi possível resolver o hostname do provider.", retryable=True) from exc
        for info in infos:
            try:
                address = ipaddress.ip_address(info[4][0])
            except ValueError:
                continue
            if address.is_private or address.is_loopback or address.is_link_local or address.is_multicast or address.is_reserved or address.is_unspecified:
                raise IntegrationError("INTEGRATION_SSRF_BLOCKED", "O hostname resolveu para endereço privado/reservado bloqueado.")

    def request_json(self, method: str, url: str, *, headers: dict[str, str], body: Any | None = None, timeout: float = 20.0, retries: int = 2) -> tuple[int, Any]:
        self._validate_dns(url)
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
        safe_headers = {**headers, "Accept": "application/json"}
        if payload is not None:
            safe_headers["Content-Type"] = "application/json"
        attempts = max(1, retries + 1 if method.upper() in {"GET", "HEAD", "PUT", "DELETE"} else 1)
        last: Exception | None = None
        for attempt in range(attempts):
            request = urllib.request.Request(url, data=payload, method=method.upper(), headers=safe_headers)
            try:
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    raw = response.read()
                    return response.status, json.loads(raw.decode("utf-8")) if raw else None
            except urllib.error.HTTPError as exc:
                raw = exc.read().decode("utf-8", errors="replace")
                try: detail: Any = json.loads(raw) if raw else None
                except json.JSONDecodeError: detail = {"message": raw[:1000]}
                if exc.code in {408, 425, 429, 500, 502, 503, 504} and attempt + 1 < attempts:
                    time.sleep(min(0.25 * (2**attempt), 2.0)); continue
                raise IntegrationError("INTEGRATION_HTTP_ERROR", f"Provider retornou HTTP {exc.code}: {detail}", retryable=exc.code >= 500 or exc.code == 429, status=exc.code) from exc
            except (urllib.error.URLError, TimeoutError) as exc:
                last = exc
                if attempt + 1 < attempts:
                    time.sleep(min(0.25 * (2**attempt), 2.0)); continue
                raise IntegrationError("INTEGRATION_NETWORK_ERROR", "Não foi possível alcançar o provider configurado.", retryable=True) from exc
        raise IntegrationError("INTEGRATION_NETWORK_ERROR", str(last or "Falha de transporte"), retryable=True)

    def request_bytes(self, method: str, url: str, *, headers: dict[str, str], timeout: float = 30.0, retries: int = 2) -> tuple[int, bytes]:
        self._validate_dns(url)
        safe_headers = {**headers, "Accept": "text/csv,text/plain;q=0.9,*/*;q=0.1"}
        attempts = max(1, retries + 1 if method.upper() in {"GET", "HEAD"} else 1)
        for attempt in range(attempts):
            req = urllib.request.Request(url, method=method.upper(), headers=safe_headers)
            try:
                with urllib.request.urlopen(req, timeout=timeout) as response:
                    return response.status, response.read()
            except urllib.error.HTTPError as exc:
                if exc.code in {408, 425, 429, 500, 502, 503, 504} and attempt + 1 < attempts:
                    time.sleep(min(0.25 * (2**attempt), 2.0)); continue
                raise IntegrationError("INTEGRATION_HTTP_ERROR", f"Provider retornou HTTP {exc.code}.", retryable=exc.code >= 500 or exc.code == 429, status=exc.code) from exc
            except (urllib.error.URLError, TimeoutError) as exc:
                if attempt + 1 < attempts:
                    time.sleep(min(0.25 * (2**attempt), 2.0)); continue
                raise IntegrationError("INTEGRATION_NETWORK_ERROR", "Não foi possível alcançar o provider configurado.", retryable=True) from exc
        raise IntegrationError("INTEGRATION_NETWORK_ERROR", "Falha de transporte.", retryable=True)

    def request_form(self, method: str, url: str, *, headers: dict[str, str], form: dict[str, str], timeout: float = 20.0, retries: int = 0) -> tuple[int, Any]:
        self._validate_dns(url)
        payload = urllib.parse.urlencode(form).encode("utf-8")
        safe_headers = {**headers, "Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"}
        attempts = max(1, retries + 1 if method.upper() in {"GET", "HEAD", "PUT", "DELETE"} else 1)
        for attempt in range(attempts):
            req = urllib.request.Request(url, data=payload, method=method.upper(), headers=safe_headers)
            try:
                with urllib.request.urlopen(req, timeout=timeout) as response:
                    raw = response.read()
                    return response.status, json.loads(raw.decode("utf-8")) if raw else None
            except urllib.error.HTTPError as exc:
                raw = exc.read().decode("utf-8", errors="replace")
                try:
                    detail: Any = json.loads(raw) if raw else None
                except json.JSONDecodeError:
                    detail = {"message": raw[:1000]}
                if exc.code in {408, 425, 429, 500, 502, 503, 504} and attempt + 1 < attempts:
                    time.sleep(min(0.25 * (2**attempt), 2.0)); continue
                raise IntegrationError("INTEGRATION_HTTP_ERROR", f"Provider retornou HTTP {exc.code}: {detail}", retryable=exc.code >= 500 or exc.code == 429, status=exc.code) from exc
            except (urllib.error.URLError, TimeoutError) as exc:
                if attempt + 1 < attempts:
                    time.sleep(min(0.25 * (2**attempt), 2.0)); continue
                raise IntegrationError("INTEGRATION_NETWORK_ERROR", "Não foi possível alcançar o provider configurado.", retryable=True) from exc
        raise IntegrationError("INTEGRATION_NETWORK_ERROR", "Falha de transporte.", retryable=True)


@dataclass(frozen=True, slots=True)
class ProviderHealth:
    status: str
    provider: str
    latency_ms: int
    details: dict[str, Any]


class BaseProvider:
    provider_name = "base"

    def __init__(self, *, config: dict[str, Any], secret: str, transport: Transport | None = None):
        self.config = config
        self.secret = secret
        self.transport = transport or UrlLibTransport(allow_private_network=bool(config.get("allow_private_network", False)))

    @staticmethod
    def _https_base(config: dict[str, Any], key: str, *, default: str = "") -> str:
        value = str(config.get(key) or default).rstrip("/")
        parsed = urllib.parse.urlparse(value)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise IntegrationError("INTEGRATION_BASE_URL_INVALID", f"{key} deve ser uma URL HTTPS válida e sem credenciais embutidas.")
        _validate_outbound_url(value, allow_private_network=bool(config.get("allow_private_network", False)))
        return value

    def health(self) -> ProviderHealth:
        raise NotImplementedError


class CloudflareProvider(BaseProvider):
    provider_name = "cloudflare"

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self.base = self._https_base(self.config, "base_url", default="https://api.cloudflare.com/client/v4")
        self.headers = {"Authorization": f"Bearer {self.secret}"}

    def health(self) -> ProviderHealth:
        started = time.perf_counter()
        status, payload = self.transport.request_json("GET", f"{self.base}/user/tokens/verify", headers=self.headers, retries=2)
        success = status == 200 and isinstance(payload, dict) and payload.get("success") is True
        token_state = ((payload or {}).get("result") or {}).get("status") if isinstance(payload, dict) else None
        return ProviderHealth("healthy" if success and token_state in {None, "active"} else "degraded", self.provider_name, round((time.perf_counter()-started)*1000), {"token_status": token_state, "http_status": status})

    def upsert_dns_record(self, *, zone_id: str, record_type: str, name: str, content: str, proxied: bool = True, ttl: int = 1, comment: str = "PIGE360") -> dict[str, Any]:
        if not zone_id or not name or not content:
            raise IntegrationError("CLOUDFLARE_DNS_INPUT_INVALID", "zone_id, name e content são obrigatórios.")
        query = urllib.parse.urlencode({"type": record_type, "name": name})
        _, found = self.transport.request_json("GET", f"{self.base}/zones/{zone_id}/dns_records?{query}", headers=self.headers)
        records = (found or {}).get("result", []) if isinstance(found, dict) else []
        body = {"type": record_type, "name": name, "content": content, "proxied": proxied, "ttl": ttl, "comment": comment}
        if records:
            record_id = records[0]["id"]
            _, payload = self.transport.request_json("PUT", f"{self.base}/zones/{zone_id}/dns_records/{record_id}", headers=self.headers, body=body)
        else:
            _, payload = self.transport.request_json("POST", f"{self.base}/zones/{zone_id}/dns_records", headers=self.headers, body=body, retries=0)
        if not isinstance(payload, dict) or payload.get("success") is not True:
            raise IntegrationError("CLOUDFLARE_DNS_FAILED", "Cloudflare não confirmou a alteração DNS.")
        return payload.get("result") or {}

    def create_custom_hostname(self, *, zone_id: str, hostname: str, ssl_method: str = "http") -> dict[str, Any]:
        body = {"hostname": hostname, "ssl": {"method": ssl_method, "type": "dv"}}
        _, payload = self.transport.request_json("POST", f"{self.base}/zones/{zone_id}/custom_hostnames", headers=self.headers, body=body, retries=0)
        if not isinstance(payload, dict) or payload.get("success") is not True:
            raise IntegrationError("CLOUDFLARE_CUSTOM_HOSTNAME_FAILED", "Cloudflare não confirmou o Custom Hostname.")
        return payload.get("result") or {}


class MailcowProvider(BaseProvider):
    provider_name = "mailcow"

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self.base = self._https_base(self.config, "base_url")
        self.headers = {"X-API-Key": self.secret}

    def health(self) -> ProviderHealth:
        started=time.perf_counter(); path=str(self.config.get("health_path") or "/api/v1/get/status/containers")
        status,payload=self.transport.request_json("GET",f"{self.base}{path}",headers=self.headers,retries=2)
        ok=status==200 and payload is not None
        return ProviderHealth("healthy" if ok else "degraded",self.provider_name,round((time.perf_counter()-started)*1000),{"http_status":status})

    def create_mailbox(self, *, local_part: str, domain: str, display_name: str, password: str, quota_mb: int = 1024, active: bool = True) -> Any:
        body={"local_part":local_part,"domain":domain,"name":display_name,"password":password,"password2":password,"quota":quota_mb,"active":"1" if active else "0","force_pw_update":"0","tls_enforce_in":"1","tls_enforce_out":"1"}
        status,payload=self.transport.request_json("POST",f"{self.base}/api/v1/add/mailbox",headers=self.headers,body=body,retries=0)
        if status not in {200, 201} or payload is None:
            raise IntegrationError("MAILCOW_MAILBOX_CREATE_FAILED", "Mailcow não confirmou a criação da mailbox.")
        return payload

    def suspend_mailbox(self, email: str, *, active: bool) -> Any:
        body={"items":[email],"attr":{"active":"1" if active else "0"}}
        status,payload=self.transport.request_json("POST",f"{self.base}/api/v1/edit/mailbox",headers=self.headers,body=body,retries=0)
        if status not in {200, 201} or payload is None:
            raise IntegrationError("MAILCOW_MAILBOX_UPDATE_FAILED", "Mailcow não confirmou a alteração da mailbox.")
        return payload


class EvolutionProvider(BaseProvider):
    provider_name = "evolution"

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self.base = self._https_base(self.config, "base_url")
        self.headers = {"apikey": self.secret}

    def health(self) -> ProviderHealth:
        started=time.perf_counter(); path=str(self.config.get("health_path") or "/instance/fetchInstances")
        status,payload=self.transport.request_json("GET",f"{self.base}{path}",headers=self.headers,retries=2)
        return ProviderHealth("healthy" if status==200 else "degraded",self.provider_name,round((time.perf_counter()-started)*1000),{"http_status":status,"instances":len(payload) if isinstance(payload,list) else None})

    def send_text(self, *, instance: str, number: str, text: str, delay_ms: int = 0) -> Any:
        if not instance or not number or not text:
            raise IntegrationError("EVOLUTION_MESSAGE_INVALID", "instance, number e text são obrigatórios.")
        body={"number":number,"text":text,"delay":max(0,delay_ms),"linkPreview":False}
        status,payload=self.transport.request_json("POST",f"{self.base}/message/sendText/{urllib.parse.quote(instance,safe='')}",headers=self.headers,body=body,retries=0)
        if status not in {200, 201} or payload is None:
            raise IntegrationError("EVOLUTION_SEND_FAILED", "Evolution API não confirmou o envio da mensagem.")
        return payload


class SmtpEmailProvider(BaseProvider):
    provider_name = "EmailProvider"

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self.host = str(self.config.get("host") or "").strip()
        self.port = int(self.config.get("port") or 587)
        self.username = str(self.config.get("username") or "").strip()
        self.from_email = str(self.config.get("from_email") or self.username).strip()
        self.from_name = str(self.config.get("from_name") or "").strip()
        self.tls_mode = str(self.config.get("tls_mode") or "starttls").lower()
        if not self.host or not self.from_email or "@" not in self.from_email:
            raise IntegrationError("EMAIL_CONFIG_INVALID", "host e from_email válidos são obrigatórios para SMTP.")
        if self.port < 1 or self.port > 65535 or self.tls_mode not in {"starttls", "ssl"}:
            raise IntegrationError("EMAIL_CONFIG_INVALID", "Porta/tls_mode SMTP inválidos.")
        # Reaproveita a política SSRF para validar literal/hostname; o transporte
        # fake de teste não resolve DNS nem abre socket.
        _validate_outbound_url(f"https://{self.host}", allow_private_network=bool(self.config.get("allow_private_network", False)))

    def _fake(self) -> Any | None:
        return self.transport if hasattr(self.transport, "send_email") else None

    def _connect(self):
        allow_private = bool(self.config.get("allow_private_network", False))
        if not allow_private:
            try:
                infos = socket.getaddrinfo(self.host, self.port, type=socket.SOCK_STREAM)
            except socket.gaierror as exc:
                raise IntegrationError("EMAIL_DNS_ERROR", "Não foi possível resolver o servidor SMTP.", retryable=True) from exc
            for info in infos:
                address = ipaddress.ip_address(info[4][0])
                if address.is_private or address.is_loopback or address.is_link_local or address.is_reserved or address.is_unspecified:
                    raise IntegrationError("INTEGRATION_SSRF_BLOCKED", "Servidor SMTP resolveu para endereço privado/reservado bloqueado.")
        context = ssl.create_default_context()
        try:
            if self.tls_mode == "ssl":
                client = smtplib.SMTP_SSL(self.host, self.port, timeout=float(self.config.get("timeout", 20)), context=context)
            else:
                client = smtplib.SMTP(self.host, self.port, timeout=float(self.config.get("timeout", 20)))
                client.ehlo(); client.starttls(context=context); client.ehlo()
            if self.username:
                client.login(self.username, self.secret)
            return client
        except (OSError, smtplib.SMTPException) as exc:
            raise IntegrationError("EMAIL_CONNECTION_FAILED", "Falha ao conectar/autenticar no SMTP configurado.", retryable=True) from exc

    def health(self) -> ProviderHealth:
        started = time.perf_counter(); fake = self._fake()
        if fake is not None and hasattr(fake, "smtp_health"):
            ok, details = fake.smtp_health(self.config)
            return ProviderHealth("healthy" if ok else "degraded", self.provider_name, round((time.perf_counter()-started)*1000), dict(details or {}))
        client = self._connect()
        try:
            code, _ = client.noop(); ok = 200 <= int(code) < 300
        finally:
            try: client.quit()
            except Exception: client.close()
        return ProviderHealth("healthy" if ok else "degraded", self.provider_name, round((time.perf_counter()-started)*1000), {"smtp_code": int(code)})

    def send_message(self, *, to: str, subject: str, text: str, html: str | None = None) -> dict[str, Any]:
        if "@" not in to or not text:
            raise IntegrationError("EMAIL_MESSAGE_INVALID", "Destinatário e conteúdo do e-mail são obrigatórios.")
        fake = self._fake()
        if fake is not None:
            result = fake.send_email({"from": self.from_email, "to": to, "subject": subject, "text": text, "html": html})
            return result if isinstance(result, dict) else {"message_id": str(result)}
        message = EmailMessage()
        message["From"] = f"{self.from_name} <{self.from_email}>" if self.from_name else self.from_email
        message["To"] = to; message["Subject"] = subject
        message.set_content(text)
        if html:
            message.add_alternative(html, subtype="html")
        client = self._connect()
        try:
            refused = client.send_message(message)
            if refused:
                raise IntegrationError("EMAIL_RECIPIENT_REFUSED", "Servidor SMTP recusou um ou mais destinatários.")
        except (OSError, smtplib.SMTPException) as exc:
            raise IntegrationError("EMAIL_SEND_FAILED", "Falha no envio SMTP.", retryable=True) from exc
        finally:
            try: client.quit()
            except Exception: client.close()
        return {"message_id": message.get("Message-ID"), "accepted": True}



class WWSoftwaresCsvProvider(BaseProvider):
    provider_name = "WWSoftwaresCsvProvider"
    UFS = frozenset("AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split())

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self.base = self._https_base(self.config, "base_url", default="https://ibpt.wwsoftwares.com.br")
        self.uf_path = str(self.config.get("uf_path") or "/tabela/ibpt/{uf}")
        if "{uf}" not in self.uf_path or not self.uf_path.startswith("/"):
            raise IntegrationError("IBPT_PATH_INVALID", "uf_path do IBPT deve iniciar com / e conter {uf}.")

    def _url(self, uf: str) -> str:
        normalized = uf.strip().upper()
        if normalized not in self.UFS:
            raise IntegrationError("IBPT_UF_INVALID", "UF inválida para sincronização IBPT.")
        return f"{self.base}{self.uf_path.format(uf=normalized.lower())}"

    def health(self) -> ProviderHealth:
        started = time.perf_counter()
        status, raw = self.transport.request_bytes("GET", self._url(str(self.config.get("health_uf") or "BA")), headers={}, retries=1)
        return ProviderHealth("healthy" if status == 200 and bool(raw.strip()) else "degraded", self.provider_name, round((time.perf_counter()-started)*1000), {"http_status": status, "bytes": len(raw)})

    def fetch_uf(self, uf: str) -> tuple[str, bytes]:
        url = self._url(uf)
        status, raw = self.transport.request_bytes("GET", url, headers={}, retries=2)
        if status != 200 or not raw.strip():
            raise IntegrationError("IBPT_DOWNLOAD_FAILED", f"IBPT não retornou CSV válido para {uf.upper()}.", retryable=status >= 500)
        return url, raw

class FiscalApiProvider(BaseProvider):
    """Adapter fiscal HTTPS tipado.

    O contrato normaliza gateways/serviços fiscais configurados pelo tenant sem
    declarar homologação com SEFAZ/município por mera configuração. Providers
    oficiais específicos podem manter este contrato e trocar apenas o transporte.
    """
    provider_name = "fiscal-api"

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self.base = self._https_base(self.config, "base_url")
        auth_header = str(self.config.get("auth_header") or "Authorization")
        auth_scheme = str(self.config.get("auth_scheme") or "Bearer").strip()
        self.headers = {auth_header: f"{auth_scheme} {self.secret}".strip()} if self.secret else {}

    def health(self) -> ProviderHealth:
        started = time.perf_counter()
        path = str(self.config.get("health_path") or "/health")
        status, payload = self.transport.request_json("GET", f"{self.base}{path}", headers=self.headers, retries=2)
        ok = status == 200
        return ProviderHealth(
            "healthy" if ok else "degraded", self.provider_name,
            round((time.perf_counter() - started) * 1000),
            {"http_status": status, "homologated": False, "transport_contract": "https-json", "provider_payload": payload if isinstance(payload, dict) else None},
        )

    @staticmethod
    def _normalize(payload: Any, *, http_status: int) -> dict[str, Any]:
        data = payload if isinstance(payload, dict) else {}
        raw_state = str(data.get("state") or data.get("status") or "").lower()
        if raw_state in {"authorized", "autorizado", "approved", "success", "succeeded"}:
            state = "authorized"
        elif raw_state in {"rejected", "rejeitado", "denied", "error", "failed"} or http_status >= 400:
            state = "rejected"
        else:
            state = "processing"
        return {
            "state": state,
            "provider_document_id": data.get("provider_document_id") or data.get("id"),
            "provider_event_id": data.get("provider_event_id") or data.get("event_id"),
            "access_key": data.get("access_key") or data.get("chave") or data.get("key"),
            "protocol": data.get("protocol") or data.get("protocolo"),
            "number": data.get("number") or data.get("numero"),
            "series": data.get("series") or data.get("serie"),
            "xml": data.get("xml"),
            "xml_base64": data.get("xml_base64"),
            "pdf_base64": data.get("pdf_base64"),
            "error_code": data.get("error_code") or data.get("code") if state == "rejected" else None,
            "error_message": data.get("error_message") or data.get("message") if state == "rejected" else None,
            "raw": data,
        }

    def issue_document(self, *, document_type: str, document: dict[str, Any]) -> dict[str, Any]:
        path = str(self.config.get("issue_path") or "/v1/fiscal/documents")
        status, payload = self.transport.request_json(
            "POST", f"{self.base}{path}", headers=self.headers,
            body={"document_type": document_type, "document": document}, retries=0,
        )
        return self._normalize(payload, http_status=status)

    def cancel_document(self, *, provider_document_id: str, reason: str, access_key: str | None = None) -> dict[str, Any]:
        template = str(self.config.get("cancel_path") or "/v1/fiscal/documents/{id}/cancel")
        path = template.replace("{id}", urllib.parse.quote(provider_document_id, safe=""))
        status, payload = self.transport.request_json(
            "POST", f"{self.base}{path}", headers=self.headers,
            body={"reason": reason, "access_key": access_key}, retries=0,
        )
        result = self._normalize(payload, http_status=status)
        raw = result.get("raw") if isinstance(result.get("raw"), dict) else {}
        raw_state = str(raw.get("state") or raw.get("status") or "").lower()
        if raw_state in {"cancelled", "canceled", "cancelado", "success", "succeeded"}:
            result["state"] = "cancelled"
        return result

    def query_document(self, *, provider_document_id: str, access_key: str | None = None) -> dict[str, Any]:
        template = str(self.config.get("query_path") or "/v1/fiscal/documents/{id}")
        path = template.replace("{id}", urllib.parse.quote(provider_document_id, safe=""))
        status, payload = self.transport.request_json(
            "GET", f"{self.base}{path}", headers=self.headers, body=None, retries=2,
        )
        return self._normalize(payload, http_status=status)

    def substitute_document(self, *, provider_document_id: str, document_type: str, document: dict[str, Any], reason: str) -> dict[str, Any]:
        template = str(self.config.get("substitute_path") or "/v1/fiscal/documents/{id}/substitute")
        path = template.replace("{id}", urllib.parse.quote(provider_document_id, safe=""))
        status, payload = self.transport.request_json(
            "POST", f"{self.base}{path}", headers=self.headers,
            body={"document_type": document_type, "document": document, "reason": reason}, retries=0,
        )
        return self._normalize(payload, http_status=status)

    def inutilize_numbers(self, *, document_type: str, year: int, series: str, start_number: int, end_number: int, reason: str) -> dict[str, Any]:
        path = str(self.config.get("inutilize_path") or "/v1/fiscal/inutilizations")
        status, payload = self.transport.request_json(
            "POST", f"{self.base}{path}", headers=self.headers,
            body={"document_type": document_type, "year": year, "series": series, "start_number": start_number, "end_number": end_number, "reason": reason}, retries=0,
        )
        data = payload if isinstance(payload, dict) else {}
        raw_state = str(data.get("state") or data.get("status") or "").lower()
        if raw_state in {"authorized", "approved", "success", "succeeded", "inutilized", "inutilizado"}:
            state = "authorized"
        elif raw_state in {"rejected", "denied", "error", "failed", "rejeitado"} or status >= 400:
            state = "rejected"
        else:
            state = "processing"
        return {
            "state": state, "protocol": data.get("protocol") or data.get("protocolo"),
            "provider_request_id": data.get("id") or data.get("request_id"),
            "error_code": data.get("error_code") or data.get("code") if state == "rejected" else None,
            "error_message": data.get("error_message") or data.get("message") if state == "rejected" else None,
            "raw": data,
        }

    def register_event(self, *, provider_document_id: str, event_type: str, payload: dict[str, Any], reason: str) -> dict[str, Any]:
        template = str(self.config.get("event_path") or "/v1/fiscal/documents/{id}/events")
        path = template.replace("{id}", urllib.parse.quote(provider_document_id, safe=""))
        status, response = self.transport.request_json(
            "POST", f"{self.base}{path}", headers=self.headers,
            body={"event_type": event_type, "payload": payload, "reason": reason}, retries=0,
        )
        data = response if isinstance(response, dict) else {}
        raw_state = str(data.get("state") or data.get("status") or "").lower()
        if raw_state in {"authorized", "accepted", "approved", "success", "succeeded"}:
            state = "authorized"
        elif raw_state in {"rejected", "denied", "error", "failed"} or status >= 400:
            state = "rejected"
        else:
            state = "processing"
        return {
            "state": state, "protocol": data.get("protocol") or data.get("protocolo"),
            "provider_event_id": data.get("event_id") or data.get("id"),
            "xml": data.get("xml"), "xml_base64": data.get("xml_base64"),
            "error_code": data.get("error_code") or data.get("code") if state == "rejected" else None,
            "error_message": data.get("error_message") or data.get("message") if state == "rejected" else None,
            "raw": data,
        }




class GovernmentEducationProvider(BaseProvider):
    """Contrato HTTPS para MEC/INEP/Educacenso e adapters equivalentes.

    O adapter nunca transforma mera resposta HTTP em protocolo oficial: estado
    ``accepted`` só é retornado quando o provider entrega um protocolo não vazio.
    """
    provider_name = "GovernmentEducationProvider"

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self.base = self._https_base(self.config, "base_url")
        auth_header = str(self.config.get("auth_header") or "Authorization")
        auth_scheme = str(self.config.get("auth_scheme") or "Bearer").strip()
        self.headers = {auth_header: f"{auth_scheme} {self.secret}".strip()} if self.secret else {}

    def health(self) -> ProviderHealth:
        started = time.perf_counter()
        path = str(self.config.get("health_path") or "/health")
        status, payload = self.transport.request_json("GET", f"{self.base}{path}", headers=self.headers, retries=2)
        return ProviderHealth(
            "healthy" if status == 200 else "degraded", self.provider_name,
            round((time.perf_counter() - started) * 1000),
            {"http_status": status, "homologated": False, "provider_payload": payload if isinstance(payload, dict) else None},
        )

    def submit_export(self, *, metadata: dict[str, Any], content: bytes, sha256: str) -> dict[str, Any]:
        import base64
        path = str(self.config.get("submission_path") or "/v1/government-education/submissions")
        status, payload = self.transport.request_json(
            "POST", f"{self.base}{path}", headers=self.headers,
            body={"metadata": metadata, "sha256": sha256, "content_base64": base64.b64encode(content).decode("ascii")}, retries=0,
        )
        data = payload if isinstance(payload, dict) else {}
        raw_state = str(data.get("state") or data.get("status") or "").strip().lower()
        protocol = str(data.get("protocol") or data.get("protocolo") or "").strip() or None
        if raw_state in {"accepted", "approved", "success", "succeeded", "aceito"} and protocol:
            state = "accepted"
        elif raw_state in {"rejected", "denied", "failed", "error", "rejeitado"} or status >= 400:
            state = "rejected"
        else:
            state = "processing"
        return {
            "state": state,
            "protocol": protocol,
            "provider_status": raw_state or str(status),
            "provider_submission_id": data.get("submission_id") or data.get("id"),
            "message": data.get("message") or data.get("mensagem"),
            "receipt": {k:v for k,v in data.items() if k not in {"token","access_token","secret","content_base64"}},
        }

class SefazNfeProvider(FiscalApiProvider):
    provider_name = "SefazNfeProvider"


class SefazNfceProvider(FiscalApiProvider):
    provider_name = "SefazNfceProvider"


class NationalNfseProvider(FiscalApiProvider):
    provider_name = "NationalNfseProvider"


class MunicipalNfseProvider(FiscalApiProvider):
    provider_name = "MunicipalNfseProvider"


class ThirdPartyFiscalProvider(FiscalApiProvider):
    provider_name = "ThirdPartyFiscalProvider"


PROVIDERS: dict[str, type[BaseProvider]] = {
    "cloudflare": CloudflareProvider,
    "CloudflareDnsProvider": CloudflareProvider,
    "mailcow": MailcowProvider,
    "MailcowProvider": MailcowProvider,
    "evolution": EvolutionProvider,
    "EvolutionApiProvider": EvolutionProvider,
    "smtp": SmtpEmailProvider,
    "EmailProvider": SmtpEmailProvider,
    "SmtpEmailProvider": SmtpEmailProvider,
    "WWSoftwaresCsvProvider": WWSoftwaresCsvProvider,
    "wwsoftwares": WWSoftwaresCsvProvider,
    "ibpt": WWSoftwaresCsvProvider,
    "SefazNfeProvider": SefazNfeProvider,
    "SefazNfceProvider": SefazNfceProvider,
    "NationalNfseProvider": NationalNfseProvider,
    "MunicipalNfseProvider": MunicipalNfseProvider,
    "ThirdPartyFiscalProvider": ThirdPartyFiscalProvider,
    "GovernmentEducationProvider": GovernmentEducationProvider,
    "inep": GovernmentEducationProvider,
    "mec": GovernmentEducationProvider,
    "educacenso": GovernmentEducationProvider,
}


def build_provider(provider: str, *, config: dict[str, Any], secret: str, transport: Transport | None = None) -> BaseProvider:
    cls = PROVIDERS.get(provider)
    if not cls:
        raise IntegrationError("INTEGRATION_PROVIDER_UNSUPPORTED", f"Provider não suportado para execução: {provider}.")
    return cls(config=config, secret=secret, transport=transport)
