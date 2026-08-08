from __future__ import annotations

from typing import Any


class FakeTransport:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def request_json(self, method: str, url: str, *, headers: dict[str, str], body: Any | None = None, timeout: float = 20.0, retries: int = 2):
        self.calls.append({"method": method, "url": url, "headers": dict(headers), "body": body, "retries": retries})
        if url.endswith("/user/tokens/verify"):
            return 200, {"success": True, "result": {"status": "active"}}
        if "/dns_records?" in url:
            return 200, {"success": True, "result": []}
        if url.endswith("/dns_records") and method == "POST":
            return 200, {"success": True, "result": {"id": "dns-1", **(body or {})}}
        if url.endswith("/custom_hostnames"):
            return 201, {"success": True, "result": {"id": "ch-1", "hostname": body["hostname"], "status": "pending", "ssl": {"status": "pending_validation"}}}
        if url.endswith("/api/v1/get/status/containers"):
            return 200, [{"type": "success"}]
        if url.endswith("/api/v1/add/mailbox"):
            return 200, [{"type": "success", "msg": "mailbox_added"}]
        if url.endswith("/api/v1/edit/mailbox"):
            return 200, [{"type": "success", "msg": "mailbox_modified"}]
        if url.endswith("/instance/fetchInstances"):
            return 200, [{"instance": {"instanceName": "school"}}]
        if "/message/sendText/" in url:
            return 201, {"key": {"id": "wamid-local-1"}, "status": "PENDING"}
        raise AssertionError(f"FakeTransport sem fixture para {method} {url}")


def _secret(local_env, name: str, value: str = "local-secret-value") -> None:
    root = local_env.root / "integration-secrets"
    root.mkdir(parents=True, exist_ok=True)
    (root / name).write_text(value, encoding="utf-8")


def _connection(local_env, provider: str, name: str, capabilities: list[str], secret_reference: str, config: dict[str, Any]) -> dict[str, Any]:
    response = local_env.client.post(
        "/api/v1/integration-connections",
        headers=local_env.alpha_headers(),
        json={
            "provider": provider,
            "name": name,
            "environment": "homologation",
            "capabilities": capabilities,
            "secret_reference": secret_reference,
            "config": config,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_providers_health_actions_and_idempotency(local_env):
    transport = FakeTransport()
    local_env.client.app.state.integration_transport = transport
    _secret(local_env, "cloudflare-token")
    _secret(local_env, "mailcow-key")
    _secret(local_env, "evolution-key")

    cloudflare = _connection(local_env, "cloudflare", "Cloudflare principal", ["dns", "custom_hostnames"], "cloudflare-token", {})
    mailcow = _connection(local_env, "mailcow", "Mail institucional", ["mailboxes"], "mailcow-key", {"base_url": "https://mail.example.edu.br"})
    evolution = _connection(local_env, "evolution", "WhatsApp", ["send_text"], "evolution-key", {"base_url": "https://whatsapp.example.edu.br"})

    for item in (cloudflare, mailcow, evolution):
        response = local_env.client.post(f"/api/v1/integration-connections/{item['id']}/test", headers=local_env.alpha_headers())
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "healthy"

    headers = local_env.alpha_headers(**{"Idempotency-Key": "dns-operation-001"})
    first = local_env.client.post(
        f"/api/v1/integration-connections/{cloudflare['id']}/cloudflare/dns",
        headers=headers,
        json={"zone_id": "zone-123", "record_type": "CNAME", "name": "app.escola.example", "content": "tenant.school.example", "proxied": True, "ttl": 1},
    )
    assert first.status_code == 200, first.text
    calls_after_first = len(transport.calls)
    replay = local_env.client.post(
        f"/api/v1/integration-connections/{cloudflare['id']}/cloudflare/dns",
        headers=headers,
        json={"zone_id": "zone-123", "record_type": "CNAME", "name": "app.escola.example", "content": "tenant.school.example", "proxied": True, "ttl": 1},
    )
    assert replay.status_code == 200, replay.text
    assert replay.json() == first.json()
    assert len(transport.calls) == calls_after_first, "replay idempotente não pode chamar o provider novamente"

    custom = local_env.client.post(
        f"/api/v1/integration-connections/{cloudflare['id']}/cloudflare/custom-hostnames",
        headers=local_env.alpha_headers(**{"Idempotency-Key": "hostname-operation-001"}),
        json={"zone_id": "zone-123", "hostname": "portal.colegio.example", "ssl_method": "http"},
    )
    assert custom.status_code == 200, custom.text
    assert custom.json()["custom_hostname_id"] == "ch-1"

    mailbox = local_env.client.post(
        f"/api/v1/integration-connections/{mailcow['id']}/mailcow/mailboxes",
        headers=local_env.alpha_headers(**{"Idempotency-Key": "mailbox-operation-001"}),
        json={"local_part": "prof.joao", "domain": "escola.example", "display_name": "Professor João", "password": "Senha-Temporaria-2026!", "quota_mb": 2048},
    )
    assert mailbox.status_code == 200, mailbox.text
    assert mailbox.json() == {"connection_id": mailcow["id"], "email": "prof.joao@escola.example", "state": "provisioned"}

    suspended = local_env.client.patch(
        f"/api/v1/integration-connections/{mailcow['id']}/mailcow/mailboxes/prof.joao@escola.example/state",
        headers=local_env.alpha_headers(**{"Idempotency-Key": "mailbox-state-001"}),
        json={"active": False},
    )
    assert suspended.status_code == 200, suspended.text
    assert suspended.json()["state"] == "suspended"

    sent = local_env.client.post(
        f"/api/v1/integration-connections/{evolution['id']}/evolution/messages/text",
        headers=local_env.alpha_headers(**{"Idempotency-Key": "evolution-message-001"}),
        json={"instance": "school", "number": "5571999999999", "text": "Aviso institucional de teste local", "delay_ms": 0},
    )
    assert sent.status_code == 200, sent.text
    assert sent.json()["provider_message_id"] == "wamid-local-1"

    listed = local_env.client.get("/api/v1/integration-connections", headers=local_env.alpha_headers())
    assert listed.status_code == 200, listed.text
    assert all("secret_reference" not in row for row in listed.json()["items"])


def test_real_network_is_disabled_in_testing(local_env):
    _secret(local_env, "cloudflare-offline")
    connection = _connection(local_env, "cloudflare", "Cloudflare offline", ["dns"], "cloudflare-offline", {})
    # Nenhum FakeTransport injetado: o runtime de teste deve bloquear I/O externo.
    response = local_env.client.post(f"/api/v1/integration-connections/{connection['id']}/test", headers=local_env.alpha_headers())
    assert response.status_code == 409, response.text
    assert response.json()["code"] == "INTEGRATION_REMOTE_DISABLED"


def test_secret_reference_path_traversal_is_rejected(local_env):
    connection = _connection(local_env, "cloudflare", "Cloudflare inválido", ["dns"], "../secret", {})
    response = local_env.client.post(f"/api/v1/integration-connections/{connection['id']}/test", headers=local_env.alpha_headers())
    assert response.status_code == 424, response.text
    assert response.json()["code"] == "INTEGRATION_SECRET_REFERENCE_INVALID"


def test_capability_and_tenant_scope_are_enforced(local_env):
    transport = FakeTransport()
    local_env.client.app.state.integration_transport = transport
    _secret(local_env, "evolution-limited")
    connection = _connection(local_env, "evolution", "Evolution limitada", [], "evolution-limited", {"base_url": "https://whatsapp.example.edu.br"})

    forbidden = local_env.client.post(
        f"/api/v1/integration-connections/{connection['id']}/evolution/messages/text",
        headers=local_env.alpha_headers(**{"Idempotency-Key": "capability-check-001"}),
        json={"instance": "school", "number": "5571999999999", "text": "Não deve enviar"},
    )
    assert forbidden.status_code == 403, forbidden.text
    assert forbidden.json()["code"] == "INTEGRATION_CAPABILITY_NOT_ENABLED"

    cross = local_env.client.get(f"/api/v1/integration-connections/{connection['id']}/health", headers=local_env.beta_headers())
    assert cross.status_code == 404, cross.text
