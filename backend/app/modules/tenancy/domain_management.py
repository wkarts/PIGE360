from __future__ import annotations

import hashlib
import os
import secrets
import ssl
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

from app.shared.integrations.providers import CloudflareProvider, IntegrationError, UrlLibTransport


class DomainLifecycleError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def normalize_hostname(value: str) -> str:
    host = value.strip().lower().rstrip(".")
    if not host or len(host) > 253 or "." not in host:
        raise DomainLifecycleError("DOMAIN_INVALID", "Domínio personalizado inválido.")
    labels = host.split(".")
    if any(not label or len(label) > 63 or label[0] == "-" or label[-1] == "-" for label in labels):
        raise DomainLifecycleError("DOMAIN_INVALID", "Domínio personalizado inválido.")
    allowed = set("abcdefghijklmnopqrstuvwxyz0123456789-")
    if any(any(ch not in allowed for ch in label) for label in labels):
        raise DomainLifecycleError("DOMAIN_INVALID", "Use o domínio em ASCII/Punycode válido.")
    return host


def verification_challenge(hostname: str) -> tuple[str, str]:
    host = normalize_hostname(hostname)
    token = "pige360=" + secrets.token_urlsafe(32)
    return f"_pige360-verification.{host}", token


def _default_txt_lookup(name: str) -> set[str]:
    try:
        import dns.resolver
    except ImportError as exc:
        raise DomainLifecycleError("DNS_RESOLVER_UNAVAILABLE", "Resolver DNS TXT indisponível no runtime.") from exc
    try:
        answers = dns.resolver.resolve(name, "TXT", lifetime=8.0)
    except Exception as exc:
        raise DomainLifecycleError("DOMAIN_DNS_NOT_READY", "Registro TXT de verificação ainda não foi localizado.") from exc
    values: set[str] = set()
    for answer in answers:
        strings = getattr(answer, "strings", None)
        if strings:
            values.add(b"".join(strings).decode("utf-8", errors="replace"))
        else:
            values.add(str(answer).strip('"'))
    return values


def verify_dns_txt(name: str, token: str, *, lookup: Callable[[str], set[str]] | None = None) -> bool:
    return token in (lookup or _default_txt_lookup)(name)


def _read_secret(file_env: str) -> str:
    filename = os.getenv(file_env, "").strip()
    if not filename:
        return ""
    path = Path(filename)
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8").strip()


def cloudflare_saas_enabled() -> bool:
    return os.getenv("CLOUDFLARE_SAAS_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}


def _dynamic_dir() -> Path | None:
    value = os.getenv("PIGE360_TRAEFIK_DYNAMIC_DIR_INTERNAL", "").strip()
    return Path(value) if value else None


def _route_name(hostname: str) -> str:
    return hashlib.sha256(normalize_hostname(hostname).encode("utf-8")).hexdigest()[:16]


def ensure_edge_route(hostname: str) -> str | None:
    directory = _dynamic_dir()
    if directory is None:
        return None
    host = normalize_hostname(hostname)
    directory.mkdir(parents=True, exist_ok=True)
    route_id = _route_name(host)
    target = directory / f"tenant-domain-{route_id}.yaml"
    content = f'''http:
  routers:
    tenant-custom-api-{route_id}:
      rule: "Host(`{host}`) && PathPrefix(`/api`)"
      entryPoints: [websecure]
      service: pige360-api@docker
      priority: 70
      tls:
        certResolver: public
    tenant-custom-web-{route_id}:
      rule: "Host(`{host}`)"
      entryPoints: [websecure]
      service: pige360-web@docker
      priority: 30
      tls:
        certResolver: public
'''
    temporary = target.with_suffix(".yaml.tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(target)
    return target.name


def remove_edge_route(hostname: str) -> None:
    directory = _dynamic_dir()
    if directory is None:
        return
    target = directory / f"tenant-domain-{_route_name(hostname)}.yaml"
    try:
        target.unlink()
    except FileNotFoundError:
        pass


def request_certificate(hostname: str) -> dict[str, Any]:
    host = normalize_hostname(hostname)
    ensure_edge_route(host)
    if not cloudflare_saas_enabled():
        return {
            "provider": "edge_acme",
            "provider_reference": None,
            "certificate_status": "pending",
            "status": "pending_tls",
        }
    zone_id = os.getenv("CLOUDFLARE_TENANT_ZONE_ID", "").strip()
    token = _read_secret("CLOUDFLARE_API_TOKEN_FILE")
    if not zone_id or not token:
        raise DomainLifecycleError("CLOUDFLARE_NOT_CONFIGURED", "Cloudflare for SaaS está habilitado sem zone/token configurados.")
    provider = CloudflareProvider(
        config={"base_url": "https://api.cloudflare.com/client/v4"},
        secret=token,
        transport=UrlLibTransport(),
    )
    try:
        result = provider.create_custom_hostname(zone_id=zone_id, hostname=host, ssl_method="txt")
    except IntegrationError as exc:
        raise DomainLifecycleError(exc.code, str(exc)) from exc
    ssl_state = result.get("ssl") if isinstance(result.get("ssl"), dict) else {}
    return {
        "provider": "cloudflare_saas",
        "provider_reference": result.get("id"),
        "certificate_status": ssl_state.get("status") or "pending",
        "status": "pending_tls",
    }


def _cloudflare_status(reference: str) -> dict[str, Any]:
    zone_id = os.getenv("CLOUDFLARE_TENANT_ZONE_ID", "").strip()
    token = _read_secret("CLOUDFLARE_API_TOKEN_FILE")
    if not zone_id or not token:
        raise DomainLifecycleError("CLOUDFLARE_NOT_CONFIGURED", "Cloudflare for SaaS não está configurado.")
    url = f"https://api.cloudflare.com/client/v4/zones/{zone_id}/custom_hostnames/{reference}"
    transport = UrlLibTransport()
    try:
        _, payload = transport.request_json("GET", url, headers={"Authorization": f"Bearer {token}"}, retries=2)
    except IntegrationError as exc:
        raise DomainLifecycleError(exc.code, str(exc)) from exc
    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise DomainLifecycleError("CLOUDFLARE_CUSTOM_HOSTNAME_STATUS_FAILED", "Cloudflare não retornou o estado do hostname.")
    return payload.get("result") or {}


def _edge_tls_status(hostname: str) -> dict[str, Any]:
    host = normalize_hostname(hostname)
    request = urllib.request.Request(f"https://{host}/healthz", headers={"User-Agent": "PIGE360-Domain-Control/1"})
    context = ssl.create_default_context()
    try:
        with urllib.request.urlopen(request, timeout=8.0, context=context) as response:
            active = response.status == 200
    except (urllib.error.URLError, TimeoutError, ssl.SSLError, OSError):
        active = False
    return {
        "status": "active" if active else "pending_tls",
        "certificate_status": "active" if active else "pending",
    }


def refresh_certificate(hostname: str, provider: str | None, provider_reference: str | None) -> dict[str, Any]:
    ensure_edge_route(hostname)
    if provider == "cloudflare_saas":
        if not provider_reference:
            raise DomainLifecycleError("DOMAIN_PROVIDER_REFERENCE_MISSING", "Referência do Custom Hostname ausente.")
        result = _cloudflare_status(provider_reference)
        ssl_state = result.get("ssl") if isinstance(result.get("ssl"), dict) else {}
        host_state = str(result.get("status") or "pending")
        cert_state = str(ssl_state.get("status") or "pending")
        active = host_state == "active" and cert_state == "active"
        return {
            "status": "active" if active else "pending_tls",
            "certificate_status": cert_state,
            "provider_state": host_state,
        }
    return _edge_tls_status(hostname)
