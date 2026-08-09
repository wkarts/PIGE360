from __future__ import annotations

import base64
import json
import subprocess
from datetime import UTC, datetime, timedelta
from typing import Any

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID


class SignatureFakeTransport:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.gov_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COUNTRY_NAME, "BR"), x509.NameAttribute(NameOID.COMMON_NAME, "Usuario GOVBR Fixture")])
        now = datetime.now(UTC)
        self.gov_cert = (
            x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(self.gov_key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(minutes=1))
            .not_valid_after(now + timedelta(days=30)).sign(self.gov_key, hashes.SHA256())
        )

    def request_json(self, method: str, url: str, *, headers: dict[str, str], body: Any | None = None, timeout: float = 20.0, retries: int = 2):
        self.calls.append({"kind": "json", "method": method, "url": url, "headers": headers, "body": body})
        if url == "https://sso.gov.example/.well-known/openid-configuration":
            return 200, {
                "authorization_endpoint": "https://sso.gov.example/authorize",
                "token_endpoint": "https://sso.gov.example/token",
            }
        if url == "https://assinatura.gov.example/certificate":
            return 200, {
                "certificate": base64.b64encode(self.gov_cert.public_bytes(serialization.Encoding.DER)).decode(),
                "subject": self.gov_cert.subject.rfc4514_string(),
                "serial_number": format(self.gov_cert.serial_number, "x"),
            }
        if url == "https://assinatura.gov.example/sign":
            from app.shared.signatures.pades import build_cades_bes_from_digest
            digest = base64.b64decode(str(body["hash"]), validate=True)
            cms_der = build_cades_bes_from_digest(digest, certificate=self.gov_cert, private_key=self.gov_key)
            return 200, {"pkcs7": base64.b64encode(cms_der).decode()}
        raise AssertionError(f"Sem fixture para {method} {url}")

    def request_form(self, method: str, url: str, *, headers: dict[str, str], form: dict[str, str], timeout: float = 20.0, retries: int = 0):
        self.calls.append({"kind": "form", "method": method, "url": url, "headers": headers, "form": form})
        if url == "https://sso.gov.example/token":
            return 200, {"access_token": "fixture-access-token", "token_type": "Bearer", "expires_in": 300}
        raise AssertionError(f"Sem fixture form para {method} {url}")


def _secret(local_env, name: str, value: str) -> None:
    root = local_env.root / "integration-secrets"
    root.mkdir(parents=True, exist_ok=True)
    (root / name).write_text(value, encoding="utf-8")


def _connection(local_env, *, provider: str, secret_reference: str, config: dict[str, Any]) -> str:
    response = local_env.client.post(
        "/api/v1/integration-connections",
        headers=local_env.alpha_headers(),
        json={
            "provider": provider,
            "name": f"Provider {provider}",
            "environment": "homologation",
            "capabilities": ["signature"],
            "secret_reference": secret_reference,
            "config": config,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _pkcs12_secret() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "BR"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Fixture ICP-Brasil Local"),
        x509.NameAttribute(NameOID.COMMON_NAME, "Responsável de Teste"),
    ])
    now = datetime.now(UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=30))
        .sign(key, hashes.SHA256())
    )
    password = b"fixture-p12-password"
    raw = pkcs12.serialize_key_and_certificates(
        b"pige360-fixture", key, cert, None,
        serialization.BestAvailableEncryption(password),
    )
    return json.dumps({"pkcs12_base64": base64.b64encode(raw).decode(), "password": password.decode()})


def _trusted_pkcs12_fixture() -> tuple[str, dict[str, Any]]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "BR"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "AC Raiz Fixture Local"),
        x509.NameAttribute(NameOID.COMMON_NAME, "AC Raiz Fixture ICP"),
    ])
    now = datetime.now(UTC)
    cert = (
        x509.CertificateBuilder().subject_name(subject).issuer_name(issuer).public_key(key.public_key())
        .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=30)).sign(key, hashes.SHA256())
    )
    password = b"fixture-trusted-password"
    raw = pkcs12.serialize_key_and_certificates(
        b"pige360-trusted-fixture", key, cert, None, serialization.BestAvailableEncryption(password)
    )
    secret = json.dumps({"pkcs12_base64": base64.b64encode(raw).decode(), "password": password.decode()})
    config = {"trust_anchors_pem_base64": [base64.b64encode(cert.public_bytes(serialization.Encoding.PEM)).decode()]}
    return secret, config


def _govbr_envelope(local_env) -> tuple[dict[str, Any], dict[str, Any]]:
    template = local_env.client.post(
        "/api/v1/contract-templates", headers=local_env.alpha_headers(),
        json={"contract_type": "educational_services", "name": "GOVBR Fixture"},
    )
    assert template.status_code == 201, template.text
    version = local_env.client.post(
        f"/api/v1/contract-templates/{template.json()['id']}/versions", headers=local_env.alpha_headers(),
        json={"body_text": "Contrato {{contract.number}}", "variables": ["contract.number"], "rules": {}},
    )
    assert version.status_code == 201, version.text
    assert local_env.client.post(f"/api/v1/contract-templates/{template.json()['id']}/publish", headers=local_env.alpha_headers()).status_code == 200
    contract = local_env.client.post(
        "/api/v1/contracts", headers=local_env.alpha_headers(),
        json={"contract_type": "educational_services", "number": "GOVBR-2026-001"},
    )
    assert contract.status_code == 201, contract.text
    generated = local_env.client.post(
        f"/api/v1/contracts/{contract.json()['id']}/generate", headers=local_env.alpha_headers(),
        json={"expected_version": 1, "template_version_id": version.json()["id"], "variables": {"contract": {"number": "GOVBR-2026-001"}}, "source_references": {}},
    )
    assert generated.status_code == 200, generated.text
    approved = local_env.client.post(
        f"/api/v1/contracts/{contract.json()['id']}/approve", headers=local_env.alpha_headers(),
        json={"expected_version": generated.json()["version"], "reason": "Aprovado para GOVBR"},
    )
    assert approved.status_code == 200, approved.text
    envelope = local_env.client.post(
        f"/api/v1/contracts/{contract.json()['id']}/send-for-signature", headers=local_env.alpha_headers(),
        json={"expected_version": approved.json()["version"], "signing_order": "sequential", "signers": [{"user_id": local_env.alpha_tenant["owner"]["id"], "name": "Responsável GOVBR", "email": "owner@alpha.example.com", "role": "financial_responsible", "required": True, "order": 1}]},
    )
    assert envelope.status_code == 200, envelope.text
    return contract.json(), envelope.json()


def test_icp_brasil_provider_opens_keypair_and_reports_truthful_trust_state(local_env):
    _secret(local_env, "icp-p12", _pkcs12_secret())
    connection_id = _connection(local_env, provider="icp_brasil", secret_reference="icp-p12", config={})

    response = local_env.client.post(
        "/api/v1/signatures/providers/icp_brasil_pades/test",
        headers=local_env.alpha_headers(),
        json={"provider": "icp_brasil_pades", "connection_id": connection_id},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "healthy"
    assert data["has_private_key"] is True
    assert data["certificate_valid_now"] is True
    assert data["trust_chain_validated"] is False
    assert data["pades_embedding_validated"] is True
    assert data["validated_locally"] is True


def test_icp_brasil_detached_cms_is_cryptographically_verifiable(local_env, tmp_path):
    secret, config = _trusted_pkcs12_fixture()
    _secret(local_env, "icp-trusted", secret)
    connection_id = _connection(local_env, provider="icp_brasil", secret_reference="icp-trusted", config=config)
    contract, envelope = _govbr_envelope(local_env)

    signed = local_env.client.post(
        f"/api/v1/signature-envelopes/{envelope['id']}/icp-brasil/sign-detached",
        headers=local_env.alpha_headers(),
        json={"connection_id": connection_id},
    )
    assert signed.status_code == 200, signed.text
    result = signed.json()
    assert result["state"] == "signed"
    assert result["trust_chain_validated"] is True
    assert result["pades_embedded"] is False
    assert result["qualification_claim"] == "certificate_chain_validated_cms_detached"

    evidence = local_env.client.get(f"/api/v1/contracts/{contract['id']}/evidence", headers=local_env.alpha_headers())
    assert evidence.status_code == 200, evidence.text
    artifact = evidence.json()["envelopes"][0]["artifacts"][0]
    assert artifact["provider"] == "icp_brasil"
    assert artifact["artifact_type"] == "pkcs7_detached"

    pdf = local_env.client.get(f"/api/v1/contracts/{contract['id']}/document", headers=local_env.alpha_headers())
    assert pdf.status_code == 200, pdf.text
    storage = local_env.client.app.state.data_router.object_storage(local_env.alpha_tenant["id"])
    cms = storage.get_bytes(artifact["storage_key"])
    pdf_path = tmp_path / "contract.pdf"; sig_path = tmp_path / "contract.p7s"; out_path = tmp_path / "verified.pdf"
    pdf_path.write_bytes(pdf.content); sig_path.write_bytes(cms)
    verified = subprocess.run(
        ["openssl", "cms", "-verify", "-binary", "-inform", "DER", "-in", str(sig_path), "-content", str(pdf_path), "-noverify", "-out", str(out_path)],
        capture_output=True, text=True, check=False,
    )
    assert verified.returncode == 0, verified.stderr
    assert out_path.read_bytes() == pdf.content



def test_icp_brasil_pades_is_embedded_and_openssl_verifies_byte_range(local_env, tmp_path):
    from app.shared.signatures.pades import extract_pades_signatures

    secret, config = _trusted_pkcs12_fixture()
    _secret(local_env, "icp-pades", secret)
    connection_id = _connection(local_env, provider="icp_brasil", secret_reference="icp-pades", config=config)
    contract, envelope = _govbr_envelope(local_env)

    signed = local_env.client.post(
        f"/api/v1/signature-envelopes/{envelope['id']}/icp-brasil/sign",
        headers=local_env.alpha_headers(),
        json={"connection_id": connection_id},
    )
    assert signed.status_code == 200, signed.text
    result = signed.json()
    assert result["state"] == "signed"
    assert result["pades_embedded"] is True
    assert result["signature_profile"] == "PAdES-B-B"
    assert result["qualification_claim"] == "certificate_chain_validated_pades_b_b"
    assert len(result["signed_document_sha256"]) == 64

    current = local_env.client.get(f"/api/v1/contracts/{contract['id']}/document", headers=local_env.alpha_headers())
    original = local_env.client.get(f"/api/v1/contracts/{contract['id']}/document?original=true", headers=local_env.alpha_headers())
    assert current.status_code == 200 and original.status_code == 200
    assert current.headers["x-pige360-document-revision"] == "signed"
    assert original.headers["x-pige360-document-revision"] == "original"
    assert current.content != original.content
    assert current.headers["x-content-sha256"] == result["signed_document_sha256"]

    signatures = extract_pades_signatures(current.content)
    assert len(signatures) == 1
    signature = signatures[0]
    assert signature["valid"] is True
    assert signature["field_name"] == result["signature_field"]
    br = signature["byte_range"]
    signed_content = current.content[:br[1]] + current.content[br[2]:br[2]+br[3]]
    cms_path = tmp_path / "embedded.der"; content_path = tmp_path / "byterange.bin"; verified_path = tmp_path / "verified.bin"
    cms_path.write_bytes(signature["cms_der"]); content_path.write_bytes(signed_content)
    verified = subprocess.run(
        ["openssl", "cms", "-verify", "-binary", "-inform", "DER", "-in", str(cms_path), "-content", str(content_path), "-noverify", "-out", str(verified_path)],
        capture_output=True, text=True, check=False,
    )
    assert verified.returncode == 0, verified.stderr
    assert verified_path.read_bytes() == signed_content

    evidence = local_env.client.get(f"/api/v1/contracts/{contract['id']}/evidence", headers=local_env.alpha_headers())
    assert evidence.status_code == 200
    artifact = evidence.json()["envelopes"][0]["artifacts"][0]
    assert artifact["artifact_type"] == "pades_pdf"
    assert artifact["metadata"]["pades_profile"] == "PAdES-B-B"
    assert artifact["metadata"]["signing_certificate_v2"] is True

def test_govbr_provider_uses_oauth_discovery_fixture_without_claiming_homologation(local_env):
    transport = SignatureFakeTransport()
    local_env.client.app.state.integration_transport = transport
    _secret(local_env, "govbr-oauth", json.dumps({"client_id": "client-local", "client_secret": "secret-local"}))
    connection_id = _connection(
        local_env,
        provider="govbr",
        secret_reference="govbr-oauth",
        config={
            "authorization_base_url": "https://sso.gov.example",
            "api_base_url": "https://assinatura.gov.example",
            "discovery_url": "https://sso.gov.example/.well-known/openid-configuration",
            "authorize_path": "/authorize",
            "token_path": "/token",
            "certificate_path": "/certificate",
            "sign_path": "/sign",
            "scope": "sign",
        },
    )

    response = local_env.client.post(
        "/api/v1/signatures/providers/govbr_advanced/test",
        headers=local_env.alpha_headers(),
        json={"provider": "govbr_advanced", "connection_id": connection_id},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "healthy"
    assert data["details"]["oauth_discovery"] is True
    assert data["homologated"] is False
    assert data["validated_locally"] is False
    assert len(transport.calls) == 1


def test_govbr_oauth_pkce_callback_embeds_pades_without_token_leak(local_env):
    transport = SignatureFakeTransport()
    local_env.client.app.state.integration_transport = transport
    _secret(local_env, "govbr-flow", json.dumps({"client_id": "client-local", "client_secret": "secret-local"}))
    connection_id = _connection(
        local_env, provider="govbr", secret_reference="govbr-flow",
        config={
            "authorization_base_url": "https://sso.gov.example",
            "api_base_url": "https://assinatura.gov.example",
            "discovery_url": "https://sso.gov.example/.well-known/openid-configuration",
            "authorize_path": "/authorize", "token_path": "/token",
            "certificate_path": "/certificate", "sign_path": "/sign", "scope": "sign",
        },
    )
    contract, envelope = _govbr_envelope(local_env)
    redirect_uri = "https://admin.alpha.school.local/assinaturas/govbr/callback"
    authorization = local_env.client.post(
        f"/api/v1/signature-envelopes/{envelope['id']}/govbr/authorize",
        headers=local_env.alpha_headers(),
        json={"connection_id": connection_id, "redirect_uri": redirect_uri},
    )
    assert authorization.status_code == 200, authorization.text
    auth_data = authorization.json()
    assert "code_challenge=" in auth_data["authorization_url"]
    assert "client_secret" not in auth_data["authorization_url"]
    assert len(auth_data["state"]) == 64

    callback = local_env.client.post(
        f"/api/v1/signature-envelopes/{envelope['id']}/govbr/callback",
        headers=local_env.alpha_headers(),
        json={
            "connection_id": connection_id, "attempt_id": auth_data["attempt_id"],
            "state": auth_data["state"], "code": "authorization-code-fixture", "redirect_uri": redirect_uri,
        },
    )
    assert callback.status_code == 200, callback.text
    result = callback.json()
    assert result["provider"] == "govbr_advanced"
    assert result["state"] == "signed"
    assert result["homologated"] is False
    assert len(result["artifact_sha256"]) == 64

    token_call = next(item for item in transport.calls if item["kind"] == "form")
    assert token_call["form"]["code"] == "authorization-code-fixture"
    assert token_call["form"]["code_verifier"]
    assert all("fixture-access-token" not in json.dumps(item) or item["url"].endswith(("/certificate", "/sign")) for item in transport.calls)

    evidence = local_env.client.get(f"/api/v1/contracts/{contract['id']}/evidence", headers=local_env.alpha_headers())
    assert evidence.status_code == 200, evidence.text
    artifacts = evidence.json()["envelopes"][0]["artifacts"]
    assert artifacts[0]["provider"] == "govbr_advanced"
    assert artifacts[0]["artifact_type"] == "pades_pdf"
    assert artifacts[0]["metadata"]["pades_profile"] == "PAdES-B-B"
    assert artifacts[0]["metadata"]["signing_certificate_v2"] is True
    from app.shared.signatures.pades import extract_pades_signatures
    final_pdf = local_env.client.get(f"/api/v1/contracts/{contract['id']}/document", headers=local_env.alpha_headers())
    assert final_pdf.status_code == 200
    signatures = extract_pades_signatures(final_pdf.content)
    assert len(signatures) == 1 and signatures[0]["valid"] is True

    replay = local_env.client.post(
        f"/api/v1/signature-envelopes/{envelope['id']}/govbr/callback",
        headers=local_env.alpha_headers(),
        json={"connection_id": connection_id, "attempt_id": auth_data["attempt_id"], "state": auth_data["state"], "code": "authorization-code-fixture", "redirect_uri": redirect_uri},
    )
    assert replay.status_code == 409, replay.text
    assert replay.json()["code"] == "GOVBR_SIGNATURE_ATTEMPT_FINALIZED"


def test_govbr_real_network_remains_blocked_in_testing(local_env):
    _secret(local_env, "govbr-offline", json.dumps({"client_id": "client-local", "client_secret": "secret-local"}))
    connection_id = _connection(
        local_env,
        provider="govbr",
        secret_reference="govbr-offline",
        config={
            "authorization_base_url": "https://sso.gov.example",
            "api_base_url": "https://assinatura.gov.example",
            "discovery_url": "https://sso.gov.example/.well-known/openid-configuration",
        },
    )
    response = local_env.client.post(
        "/api/v1/signatures/providers/govbr_advanced/test",
        headers=local_env.alpha_headers(),
        json={"provider": "govbr_advanced", "connection_id": connection_id},
    )
    assert response.status_code == 409, response.text
    assert response.json()["code"] == "INTEGRATION_REMOTE_DISABLED"


def test_icp_brasil_pades_two_signers_preserve_both_incremental_revisions(local_env):
    from app.shared.signatures.pades import extract_pades_signatures

    secret, config = _trusted_pkcs12_fixture()
    _secret(local_env, "icp-pades-multi", secret)
    connection_id = _connection(local_env, provider="icp_brasil", secret_reference="icp-pades-multi", config=config)
    second_user, second_token = local_env.create_alpha_user("second.signer@alpha.example.com", ["guardian"])

    template = local_env.client.post(
        "/api/v1/contract-templates", headers=local_env.alpha_headers(),
        json={"contract_type": "educational_services", "name": "PAdES multi"},
    )
    version = local_env.client.post(
        f"/api/v1/contract-templates/{template.json()['id']}/versions", headers=local_env.alpha_headers(),
        json={"body_text": "Contrato {{contract.number}} com dois signatários", "variables": ["contract.number"], "rules": {}},
    )
    assert local_env.client.post(f"/api/v1/contract-templates/{template.json()['id']}/publish", headers=local_env.alpha_headers()).status_code == 200
    contract = local_env.client.post(
        "/api/v1/contracts", headers=local_env.alpha_headers(),
        json={"contract_type": "educational_services", "number": "PADES-MULTI-001"},
    )
    generated = local_env.client.post(
        f"/api/v1/contracts/{contract.json()['id']}/generate", headers=local_env.alpha_headers(),
        json={"expected_version": 1, "template_version_id": version.json()["id"], "variables": {"contract": {"number": "PADES-MULTI-001"}}, "source_references": {}},
    )
    approved = local_env.client.post(
        f"/api/v1/contracts/{contract.json()['id']}/approve", headers=local_env.alpha_headers(),
        json={"expected_version": generated.json()["version"], "reason": "Aprovado para múltiplas assinaturas"},
    )
    envelope = local_env.client.post(
        f"/api/v1/contracts/{contract.json()['id']}/send-for-signature", headers=local_env.alpha_headers(),
        json={
            "expected_version": approved.json()["version"], "signing_order": "sequential",
            "signers": [
                {"user_id": local_env.alpha_tenant["owner"]["id"], "name": "Primeiro Signatário", "email": "owner@alpha.example.com", "required": True, "order": 1},
                {"user_id": second_user["id"], "name": "Segundo Signatário", "email": "second.signer@alpha.example.com", "required": True, "order": 2},
            ],
        },
    )
    assert envelope.status_code == 200, envelope.text

    first = local_env.client.post(
        f"/api/v1/signature-envelopes/{envelope.json()['id']}/icp-brasil/sign",
        headers=local_env.alpha_headers(), json={"connection_id": connection_id},
    )
    assert first.status_code == 200, first.text
    assert first.json()["state"] == "partially_signed"

    second_headers = local_env.headers("admin.alpha.school.local", second_token)
    second = local_env.client.post(
        f"/api/v1/signature-envelopes/{envelope.json()['id']}/icp-brasil/sign",
        headers=second_headers, json={"connection_id": connection_id},
    )
    assert second.status_code == 200, second.text
    assert second.json()["state"] == "signed"
    assert first.json()["signed_document_sha256"] != second.json()["signed_document_sha256"]

    final_pdf = local_env.client.get(f"/api/v1/contracts/{contract.json()['id']}/document", headers=local_env.alpha_headers())
    assert final_pdf.status_code == 200
    signatures = extract_pades_signatures(final_pdf.content)
    assert len(signatures) == 2
    assert all(item["valid"] for item in signatures)

    public_validation = local_env.client.post(
        "/api/v1/public/contracts/validate-file",
        headers={"host": "admin.alpha.school.local"},
        json={"content_base64": base64.b64encode(final_pdf.content).decode("ascii")},
    )
    assert public_validation.status_code == 200, public_validation.text
    assert public_validation.json()["authentic"] is True
    assert public_validation.json()["revision"] == "signed"
    assert public_validation.json()["signature_profile"] == "PAdES-B-B"
