from __future__ import annotations

import base64
import json
import time
import urllib.parse
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import dsa, ec, padding, rsa
from cryptography.x509 import load_pem_x509_certificate
from cryptography.hazmat.primitives.serialization import pkcs12, pkcs7

from app.shared.integrations.providers import IntegrationError, ProviderHealth, Transport, UrlLibTransport, _validate_outbound_url
from app.shared.signatures.pades import PadesError, PadesSignatureResult, extract_pades_signatures, sign_pades_b_b


def _json_secret(secret: str, provider: str) -> dict[str, Any]:
    try:
        payload = json.loads(secret)
    except json.JSONDecodeError as exc:
        raise IntegrationError(f"{provider}_SECRET_INVALID", "O segredo do provider deve ser um JSON válido.") from exc
    if not isinstance(payload, dict):
        raise IntegrationError(f"{provider}_SECRET_INVALID", "O segredo do provider deve ser um objeto JSON.")
    return payload


@dataclass(frozen=True, slots=True)
class CertificateHealth:
    status: str
    subject: str
    issuer: str
    serial_number: str
    not_valid_before: str
    not_valid_after: str
    has_private_key: bool
    chain_certificates: int
    certificate_valid_now: bool
    trust_chain_validated: bool


class IcpBrasilCertificateProvider:
    """Provider PKCS#12 local.

    Ele prova posse da chave e validade temporal do certificado. A confiança ICP-Brasil
    completa só pode ser marcada quando uma cadeia de confiança oficial for configurada;
    por isso `trust_chain_validated` permanece falso sem trust anchors explícitos.
    """

    provider_name = "icp_brasil_pades"

    def __init__(self, *, config: dict[str, Any], secret: str):
        self.config = config
        payload = _json_secret(secret, "ICP_BRASIL")
        raw = payload.get("pkcs12_base64")
        if not isinstance(raw, str) or not raw:
            raise IntegrationError("ICP_BRASIL_PKCS12_MISSING", "pkcs12_base64 não foi configurado.")
        try:
            p12 = base64.b64decode(raw, validate=True)
        except Exception as exc:
            raise IntegrationError("ICP_BRASIL_PKCS12_INVALID", "Conteúdo PKCS#12 inválido.") from exc
        password = payload.get("password")
        password_bytes = str(password).encode("utf-8") if password not in {None, ""} else None
        try:
            self.private_key, self.certificate, self.chain = pkcs12.load_key_and_certificates(p12, password_bytes)
        except Exception as exc:
            raise IntegrationError("ICP_BRASIL_PKCS12_OPEN_FAILED", "Não foi possível abrir o certificado PKCS#12 com a credencial fornecida.") from exc
        if self.private_key is None or self.certificate is None:
            raise IntegrationError("ICP_BRASIL_KEYPAIR_MISSING", "O PKCS#12 deve conter certificado e chave privada.")

    @staticmethod
    def _verify_certificate_signature(certificate, issuer_certificate) -> None:
        public_key = issuer_certificate.public_key()
        algorithm = certificate.signature_hash_algorithm
        if isinstance(public_key, rsa.RSAPublicKey):
            public_key.verify(certificate.signature, certificate.tbs_certificate_bytes, padding.PKCS1v15(), algorithm)
        elif isinstance(public_key, ec.EllipticCurvePublicKey):
            public_key.verify(certificate.signature, certificate.tbs_certificate_bytes, ec.ECDSA(algorithm))
        elif isinstance(public_key, dsa.DSAPublicKey):
            public_key.verify(certificate.signature, certificate.tbs_certificate_bytes, algorithm)
        else:
            raise IntegrationError("ICP_BRASIL_PUBLIC_KEY_UNSUPPORTED", "Algoritmo de chave pública não suportado para validação da cadeia.")

    def _trust_anchors(self):
        anchors = []
        for encoded in self.config.get("trust_anchors_pem_base64") or []:
            try:
                raw = base64.b64decode(str(encoded), validate=True)
                anchors.append(load_pem_x509_certificate(raw))
            except Exception as exc:
                raise IntegrationError("ICP_BRASIL_TRUST_ANCHOR_INVALID", "Âncora de confiança ICP-Brasil configurada é inválida.") from exc
        return anchors

    def _validate_chain(self) -> bool:
        anchors = self._trust_anchors()
        if not anchors:
            return False
        now = datetime.now(UTC)
        candidates = list(self.chain or []) + anchors
        anchor_fingerprints = {item.fingerprint(hashes.SHA256()) for item in anchors}
        current = self.certificate
        visited: set[bytes] = set()
        for _ in range(len(candidates) + 2):
            fingerprint = current.fingerprint(hashes.SHA256())
            if fingerprint in visited:
                return False
            visited.add(fingerprint)
            if not (current.not_valid_before_utc <= now <= current.not_valid_after_utc):
                return False
            if fingerprint in anchor_fingerprints:
                if current.subject == current.issuer:
                    self._verify_certificate_signature(current, current)
                return True
            issuer = next((candidate for candidate in candidates if candidate.subject == current.issuer and candidate.fingerprint(hashes.SHA256()) != fingerprint), None)
            if issuer is None:
                return False
            self._verify_certificate_signature(current, issuer)
            current = issuer
        return False

    def health(self) -> CertificateHealth:
        cert = self.certificate
        now = datetime.now(UTC)
        before = cert.not_valid_before_utc
        after = cert.not_valid_after_utc
        try:
            chain_validated = self._validate_chain()
        except Exception as exc:
            if isinstance(exc, IntegrationError):
                raise
            raise IntegrationError("ICP_BRASIL_CHAIN_VALIDATION_FAILED", "Falha criptográfica ao validar a cadeia do certificado.") from exc
        return CertificateHealth(
            status="healthy" if before <= now <= after else "expired_or_not_yet_valid",
            subject=cert.subject.rfc4514_string(),
            issuer=cert.issuer.rfc4514_string(),
            serial_number=format(cert.serial_number, "x"),
            not_valid_before=before.isoformat().replace("+00:00", "Z"),
            not_valid_after=after.isoformat().replace("+00:00", "Z"),
            has_private_key=True,
            chain_certificates=len(self.chain or []),
            certificate_valid_now=before <= now <= after,
            trust_chain_validated=chain_validated,
        )

    def sign_detached_cms(self, content: bytes) -> bytes:
        builder = pkcs7.PKCS7SignatureBuilder().set_data(content).add_signer(self.certificate, self.private_key, hashes.SHA256())
        return builder.sign(
            serialization.Encoding.DER,
            [pkcs7.PKCS7Options.DetachedSignature, pkcs7.PKCS7Options.Binary],
        )

    def sign_pades_b_b(
        self,
        pdf: bytes,
        *,
        field_name: str,
        signer_name: str | None = None,
        reason: str | None = None,
    ) -> PadesSignatureResult:
        try:
            return sign_pades_b_b(
                pdf,
                certificate=self.certificate,
                private_key=self.private_key,
                chain=list(self.chain or []),
                field_name=field_name,
                signer_name=signer_name,
                reason=reason,
            )
        except PadesError as exc:
            raise IntegrationError("ICP_BRASIL_PADES_SIGN_FAILED", str(exc)) from exc

    @staticmethod
    def validate_pades(pdf: bytes) -> list[dict[str, Any]]:
        try:
            return extract_pades_signatures(pdf)
        except PadesError as exc:
            raise IntegrationError("ICP_BRASIL_PADES_VALIDATION_FAILED", str(exc)) from exc


class GovBrAdvancedSignatureProvider:
    """Contrato OAuth 2.0 + assinatura PKCS#7 do GOV.BR.

    Paths são parametrizados porque homologação/produção e versões oficiais podem
    variar. O provider só executa rede através do Transport seguro compartilhado.
    """

    provider_name = "govbr_advanced"

    def __init__(self, *, config: dict[str, Any], secret: str, transport: Transport | None = None):
        self.config = config
        credentials = _json_secret(secret, "GOVBR")
        self.client_id = str(credentials.get("client_id") or "")
        self.client_secret = str(credentials.get("client_secret") or "")
        if not self.client_id or not self.client_secret:
            raise IntegrationError("GOVBR_CLIENT_CREDENTIALS_MISSING", "client_id/client_secret não configurados no segredo GOV.BR.")
        self.auth_base = str(config.get("authorization_base_url") or "").rstrip("/")
        self.api_base = str(config.get("api_base_url") or "").rstrip("/")
        self.discovery_url = str(config.get("discovery_url") or "")
        for value, name in ((self.auth_base, "authorization_base_url"), (self.api_base, "api_base_url"), (self.discovery_url, "discovery_url")):
            if not value:
                raise IntegrationError("GOVBR_URL_MISSING", f"{name} é obrigatório.")
            _validate_outbound_url(value, allow_private_network=bool(config.get("allow_private_network", False)))
        self.transport = transport or UrlLibTransport(allow_private_network=bool(config.get("allow_private_network", False)))

    def health(self) -> ProviderHealth:
        started = time.perf_counter()
        status, payload = self.transport.request_json("GET", self.discovery_url, headers={}, retries=2)
        valid = status == 200 and isinstance(payload, dict) and bool(payload.get("authorization_endpoint")) and bool(payload.get("token_endpoint"))
        return ProviderHealth(
            "healthy" if valid else "degraded",
            self.provider_name,
            round((time.perf_counter() - started) * 1000),
            {"http_status": status, "oauth_discovery": valid},
        )

    def authorization_url(self, *, state: str, redirect_uri: str, code_challenge: str | None = None) -> str:
        query = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "scope": str(self.config.get("scope") or "sign"),
            "state": state,
        }
        if code_challenge:
            query.update({"code_challenge": code_challenge, "code_challenge_method": "S256"})
        path = str(self.config.get("authorize_path") or "/authorize")
        return f"{self.auth_base}{path}?{urllib.parse.urlencode(query)}"

    def exchange_code(self, *, code: str, redirect_uri: str, code_verifier: str | None = None) -> dict[str, Any]:
        form = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        if code_verifier:
            form["code_verifier"] = code_verifier
        path = str(self.config.get("token_path") or "/token")
        status, payload = self.transport.request_form("POST", f"{self.auth_base}{path}", headers={}, form=form, retries=0)
        if status != 200 or not isinstance(payload, dict) or not payload.get("access_token"):
            raise IntegrationError("GOVBR_TOKEN_EXCHANGE_FAILED", "GOV.BR não retornou access_token válido.", status=status)
        return payload

    def certificate(self, *, access_token: str) -> dict[str, Any]:
        path = str(self.config.get("certificate_path") or "/certificate")
        status, payload = self.transport.request_json("GET", f"{self.api_base}{path}", headers={"Authorization": f"Bearer {access_token}"}, retries=0)
        if status != 200 or not isinstance(payload, dict):
            raise IntegrationError("GOVBR_CERTIFICATE_FAILED", "Não foi possível obter o certificado do signatário.", status=status)
        return payload

    def sign_hash(self, *, access_token: str, sha256_base64: str) -> dict[str, Any]:
        try:
            digest = base64.b64decode(sha256_base64, validate=True)
        except Exception as exc:
            raise IntegrationError("GOVBR_HASH_INVALID", "Hash SHA-256 em Base64 inválido.") from exc
        if len(digest) != 32:
            raise IntegrationError("GOVBR_HASH_INVALID", "O hash deve possuir exatamente 32 bytes SHA-256.")
        path = str(self.config.get("sign_path") or "/sign")
        body = {"hash": sha256_base64, "hash_algorithm": "SHA256"}
        status, payload = self.transport.request_json("POST", f"{self.api_base}{path}", headers={"Authorization": f"Bearer {access_token}"}, body=body, retries=0)
        if status not in {200, 201} or not isinstance(payload, dict) or not (payload.get("pkcs7") or payload.get("signature")):
            raise IntegrationError("GOVBR_SIGNATURE_FAILED", "GOV.BR não retornou uma assinatura PKCS#7 válida.", status=status)
        return payload
