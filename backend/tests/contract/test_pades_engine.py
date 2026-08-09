from __future__ import annotations

import base64
import hashlib
import json
import subprocess
from datetime import UTC, datetime, timedelta
from io import BytesIO

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from reportlab.pdfgen import canvas

from app.shared.signatures.pades import PadesError, extract_pades_signatures, sign_pades_b_b


def _fixture():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COUNTRY_NAME, "BR"), x509.NameAttribute(NameOID.COMMON_NAME, "PIGE360 PAdES Fixture")])
    now = datetime.now(UTC)
    cert = (
        x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
        .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=30)).sign(key, hashes.SHA256())
    )
    return key, cert


def _pdf() -> bytes:
    stream = BytesIO(); doc = canvas.Canvas(stream); doc.drawString(72, 720, "Contrato PIGE360 - validação PAdES"); doc.save(); return stream.getvalue()


def test_two_incremental_pades_signatures_remain_valid_and_openssl_verifies(tmp_path):
    key, cert = _fixture(); original = _pdf()
    first = sign_pades_b_b(original, certificate=cert, private_key=key, field_name="Assinatura_1", signer_name="Primeiro")
    second = sign_pades_b_b(first.pdf, certificate=cert, private_key=key, field_name="Assinatura_2", signer_name="Segundo")
    signatures = extract_pades_signatures(second.pdf)
    assert [item["field_name"] for item in signatures] == ["Assinatura_1", "Assinatura_2"]
    assert all(item["valid"] for item in signatures)
    assert first.input_sha256 == hashlib.sha256(original).hexdigest()
    assert second.input_sha256 == hashlib.sha256(first.pdf).hexdigest()
    assert second.output_sha256 == hashlib.sha256(second.pdf).hexdigest()
    for index, item in enumerate(signatures, 1):
        br = item["byte_range"]
        signed_content = second.pdf[:br[1]] + second.pdf[br[2]:br[2]+br[3]]
        cms_path = tmp_path / f"sig-{index}.der"; content_path = tmp_path / f"content-{index}.bin"; output_path = tmp_path / f"verified-{index}.bin"
        cms_path.write_bytes(item["cms_der"]); content_path.write_bytes(signed_content)
        result = subprocess.run(["openssl", "cms", "-verify", "-binary", "-inform", "DER", "-in", str(cms_path), "-content", str(content_path), "-noverify", "-out", str(output_path)], capture_output=True, text=True, check=False)
        assert result.returncode == 0, result.stderr
        assert output_path.read_bytes() == signed_content


def test_pades_detects_signed_byte_range_tampering():
    key, cert = _fixture(); signed = sign_pades_b_b(_pdf(), certificate=cert, private_key=key, field_name="Assinatura_1")
    corrupted = bytearray(signed.pdf)
    # Altera um byte dentro da primeira faixa assinada sem tocar o /Contents.
    position = signed.byte_range[1] // 2
    corrupted[position] = (corrupted[position] + 1) % 256
    with pytest.raises(PadesError):
        extract_pades_signatures(bytes(corrupted))
