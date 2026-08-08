from __future__ import annotations

import hashlib
import hmac


def signature_domain_key(secret: str) -> bytes:
    """Deriva chave de domínio sem reutilizar diretamente a chave JWT."""
    return hmac.new(secret.encode("utf-8"), b"pige360/signature-evidence/v1", hashlib.sha256).digest()


def derive_otp(secret: str, *, challenge_id: str, user_id: str) -> str:
    key = signature_domain_key(secret)
    digest = hmac.new(key, f"otp:{challenge_id}:{user_id}".encode("utf-8"), hashlib.sha256).digest()
    value = int.from_bytes(digest[:8], "big") % 1_000_000
    return f"{value:06d}"


def evidence_hmac(secret: str, canonical_payload: str) -> str:
    return hmac.new(signature_domain_key(secret), canonical_payload.encode("utf-8"), hashlib.sha256).hexdigest()
