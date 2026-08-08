from __future__ import annotations

import hashlib
import io
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from asn1crypto import cms, core, tsp, x509 as asn1_x509
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import dsa, ec, padding, rsa
from pypdf import PdfReader
from pypdf.generic import ArrayObject, DictionaryObject, IndirectObject, NameObject, NumberObject, TextStringObject


class PadesError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class PreparedPadesRevision:
    pdf: bytes
    signed_content: bytes
    byte_range: tuple[int, int, int, int]
    contents_hex_offset: int
    contents_hex_length: int
    field_name: str


@dataclass(frozen=True, slots=True)
class PadesSignatureResult:
    pdf: bytes
    cms_der: bytes
    byte_range: tuple[int, int, int, int]
    field_name: str
    profile: str
    input_sha256: str
    output_sha256: str
    signed_content_sha256: str


def _serialize_pdf_object(value: Any) -> bytes:
    stream = io.BytesIO()
    value.write_to_stream(stream, encryption_key=None)
    return stream.getvalue()


def _pdf_literal(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _last_startxref(pdf: bytes) -> int:
    matches = list(re.finditer(rb"startxref\s+(\d+)\s+%%EOF", pdf.rstrip()))
    if not matches:
        raise PadesError("PDF não possui startxref/EOF válido para revisão incremental.")
    return int(matches[-1].group(1))


def _copy_dictionary(source: DictionaryObject) -> DictionaryObject:
    clone = DictionaryObject()
    for key, value in source.items():
        clone[key] = value
    return clone


def _xref_sections(entries: dict[int, int]) -> bytes:
    out = bytearray(b"xref\n")
    numbers = sorted(entries)
    if not numbers:
        raise PadesError("Nenhum objeto foi preparado para a revisão incremental.")
    start = numbers[0]
    group = [start]
    groups: list[list[int]] = []
    for number in numbers[1:]:
        if number == group[-1] + 1:
            group.append(number)
        else:
            groups.append(group)
            group = [number]
    groups.append(group)
    for group in groups:
        out.extend(f"{group[0]} {len(group)}\n".encode("ascii"))
        for number in group:
            out.extend(f"{entries[number]:010d} 00000 n \n".encode("ascii"))
    return bytes(out)


def _build_trailer(reader: PdfReader, *, size: int, prev: int) -> bytes:
    trailer = DictionaryObject()
    trailer[NameObject("/Size")] = NumberObject(size)
    root = reader.trailer.raw_get("/Root")
    trailer[NameObject("/Root")] = root
    trailer[NameObject("/Prev")] = NumberObject(prev)
    for name in ("/Info", "/ID"):
        try:
            value = reader.trailer.raw_get(name)
        except KeyError:
            continue
        trailer[NameObject(name)] = value
    return _serialize_pdf_object(trailer)


def prepare_incremental_signature(
    pdf: bytes,
    *,
    field_name: str,
    signer_name: str | None = None,
    reason: str | None = None,
    placeholder_bytes: int = 65536,
    signing_time: datetime | None = None,
) -> PreparedPadesRevision:
    if not pdf.startswith(b"%PDF-"):
        raise PadesError("Documento não é um PDF reconhecido.")
    if placeholder_bytes < 16384:
        raise PadesError("Reserva de assinatura insuficiente; mínimo de 16 KiB.")
    try:
        reader = PdfReader(io.BytesIO(pdf), strict=False)
    except Exception as exc:
        raise PadesError("PDF não pôde ser analisado para assinatura incremental.") from exc
    if reader.is_encrypted:
        raise PadesError("PDF criptografado não é aceito pelo pipeline PAdES.")
    if not reader.pages:
        raise PadesError("PDF sem páginas não pode receber campo de assinatura.")

    previous_startxref = _last_startxref(pdf)
    try:
        size = int(reader.trailer["/Size"])
        root_ref = reader.trailer.raw_get("/Root")
        root_obj = root_ref.get_object()
        root_number = int(root_ref.idnum)
        first_page = reader.pages[0]
        page_ref = first_page.indirect_reference
        if page_ref is None:
            raise PadesError("Primeira página não possui referência indireta.")
        page_number = int(page_ref.idnum)
    except Exception as exc:
        if isinstance(exc, PadesError):
            raise
        raise PadesError("Estrutura de catálogo/página do PDF não é compatível com assinatura incremental.") from exc

    sig_number = size
    field_number = size + 1
    acro_number = size + 2
    new_size = size + 3

    sig_ref = IndirectObject(sig_number, 0, reader)
    field_ref = IndirectObject(field_number, 0, reader)
    acro_ref = IndirectObject(acro_number, 0, reader)

    # Campo invisível, mas formalmente registrado no AcroForm e na primeira página.
    field = DictionaryObject()
    field[NameObject("/Type")] = NameObject("/Annot")
    field[NameObject("/Subtype")] = NameObject("/Widget")
    field[NameObject("/FT")] = NameObject("/Sig")
    field[NameObject("/T")] = TextStringObject(field_name)
    field[NameObject("/V")] = sig_ref
    field[NameObject("/Rect")] = ArrayObject([NumberObject(0), NumberObject(0), NumberObject(0), NumberObject(0)])
    field[NameObject("/F")] = NumberObject(132)
    field[NameObject("/P")] = page_ref

    root_copy = _copy_dictionary(root_obj)
    existing_acro = root_obj.get("/AcroForm")
    if isinstance(existing_acro, IndirectObject):
        existing_acro = existing_acro.get_object()
    if isinstance(existing_acro, DictionaryObject):
        acro = _copy_dictionary(existing_acro)
        fields = acro.get("/Fields")
        if isinstance(fields, IndirectObject):
            fields = fields.get_object()
        new_fields = ArrayObject(list(fields or []))
    else:
        acro = DictionaryObject()
        new_fields = ArrayObject()
    new_fields.append(field_ref)
    acro[NameObject("/Fields")] = new_fields
    acro[NameObject("/SigFlags")] = NumberObject(3)
    root_copy[NameObject("/AcroForm")] = acro_ref

    page_obj = page_ref.get_object()
    page_copy = _copy_dictionary(page_obj)
    annots = page_obj.get("/Annots")
    if isinstance(annots, IndirectObject):
        annots = annots.get_object()
    new_annots = ArrayObject(list(annots or []))
    new_annots.append(field_ref)
    page_copy[NameObject("/Annots")] = new_annots

    timestamp = (signing_time or datetime.now(UTC)).astimezone(UTC)
    pdf_date = timestamp.strftime("D:%Y%m%d%H%M%SZ")
    byte_placeholder = "9" * 20
    contents_hex_length = placeholder_bytes * 2
    sig_dict_prefix = (
        f"{sig_number} 0 obj\n"
        "<< /Type /Sig /Filter /Adobe.PPKLite /SubFilter /ETSI.CAdES.detached "
        f"/ByteRange [0 {byte_placeholder} {byte_placeholder} {byte_placeholder}] "
        f"/M ({_pdf_literal(pdf_date)}) "
    )
    if signer_name:
        sig_dict_prefix += f"/Name ({_pdf_literal(signer_name)}) "
    if reason:
        sig_dict_prefix += f"/Reason ({_pdf_literal(reason)}) "
    sig_dict_prefix += "/Contents <"
    sig_object = sig_dict_prefix.encode("utf-8") + (b"0" * contents_hex_length) + b"> >>\nendobj\n"

    base = bytearray(pdf)
    if not base.endswith((b"\n", b"\r")):
        base.extend(b"\n")
    entries: dict[int, int] = {}

    sig_offset = len(base)
    entries[sig_number] = sig_offset
    contents_hex_offset = sig_offset + len(sig_dict_prefix.encode("utf-8"))
    base.extend(sig_object)

    for number, obj in (
        (field_number, field),
        (acro_number, acro),
        (root_number, root_copy),
        (page_number, page_copy),
    ):
        entries[number] = len(base)
        base.extend(f"{number} 0 obj\n".encode("ascii"))
        base.extend(_serialize_pdf_object(obj))
        base.extend(b"\nendobj\n")

    xref_offset = len(base)
    base.extend(_xref_sections(entries))
    base.extend(b"trailer\n")
    base.extend(_build_trailer(reader, size=new_size, prev=previous_startxref))
    base.extend(b"\nstartxref\n")
    base.extend(str(xref_offset).encode("ascii"))
    base.extend(b"\n%%EOF\n")

    # Excluir delimitadores < > e todo o /Contents da faixa assinada.
    left_angle = contents_hex_offset - 1
    right_angle = contents_hex_offset + contents_hex_length
    second_start = right_angle + 1
    byte_range = (0, left_angle, second_start, len(base) - second_start)

    placeholder_token = f"[0 {byte_placeholder} {byte_placeholder} {byte_placeholder}]".encode("ascii")
    actual_token = (
        f"[0 {byte_range[1]:020d} {byte_range[2]:020d} {byte_range[3]:020d}]".encode("ascii")
    )
    if len(actual_token) != len(placeholder_token):
        raise PadesError("ByteRange excedeu a reserva numérica do PDF.")
    token_position = base.find(placeholder_token, sig_offset, contents_hex_offset)
    if token_position < 0:
        raise PadesError("Reserva ByteRange não foi localizada na revisão incremental.")
    base[token_position : token_position + len(placeholder_token)] = actual_token

    prepared_pdf = bytes(base)
    signed_content = prepared_pdf[: byte_range[1]] + prepared_pdf[byte_range[2] : byte_range[2] + byte_range[3]]
    return PreparedPadesRevision(
        pdf=prepared_pdf,
        signed_content=signed_content,
        byte_range=byte_range,
        contents_hex_offset=contents_hex_offset,
        contents_hex_length=contents_hex_length,
        field_name=field_name,
    )


def _signature_algorithm(private_key: Any) -> tuple[str, Any]:
    if isinstance(private_key, rsa.RSAPrivateKey):
        return "sha256_rsa", padding.PKCS1v15()
    if isinstance(private_key, ec.EllipticCurvePrivateKey):
        return "sha256_ecdsa", ec.ECDSA(hashes.SHA256())
    if isinstance(private_key, dsa.DSAPrivateKey):
        return "sha256_dsa", hashes.SHA256()
    raise PadesError("Algoritmo da chave privada não é suportado para CAdES/PAdES.")


def build_cades_bes(
    content: bytes,
    *,
    certificate: x509.Certificate,
    private_key: Any,
    chain: list[x509.Certificate] | tuple[x509.Certificate, ...] | None = None,
    signing_time: datetime | None = None,
) -> bytes:
    return build_cades_bes_from_digest(
        hashlib.sha256(content).digest(), certificate=certificate, private_key=private_key, chain=chain, signing_time=signing_time
    )


def build_cades_bes_from_digest(
    digest: bytes,
    *,
    certificate: x509.Certificate,
    private_key: Any,
    chain: list[x509.Certificate] | tuple[x509.Certificate, ...] | None = None,
    signing_time: datetime | None = None,
) -> bytes:
    if len(digest) != 32:
        raise PadesError("Digest externo deve possuir exatamente 32 bytes SHA-256.")
    leaf_der = certificate.public_bytes(serialization.Encoding.DER)
    leaf = asn1_x509.Certificate.load(leaf_der)
    cert_digest = hashlib.sha256(leaf_der).digest()
    now = (signing_time or datetime.now(UTC)).astimezone(UTC).replace(microsecond=0)

    signed_attrs = cms.CMSAttributes(
        [
            cms.CMSAttribute({"type": "content_type", "values": ["data"]}),
            cms.CMSAttribute({"type": "message_digest", "values": [digest]}),
            cms.CMSAttribute({"type": "signing_time", "values": [cms.Time({"utc_time": core.UTCTime(now)})]}),
            cms.CMSAttribute(
                {
                    "type": "signing_certificate_v2",
                    "values": [tsp.SigningCertificateV2({"certs": [tsp.ESSCertIDv2({"hash_algorithm": {"algorithm": "sha256"}, "cert_hash": cert_digest})]})],
                }
            ),
        ]
    )

    algorithm, sign_parameter = _signature_algorithm(private_key)
    if isinstance(private_key, rsa.RSAPrivateKey):
        signature = private_key.sign(signed_attrs.dump(), sign_parameter, hashes.SHA256())
    elif isinstance(private_key, ec.EllipticCurvePrivateKey):
        signature = private_key.sign(signed_attrs.dump(), sign_parameter)
    elif isinstance(private_key, dsa.DSAPrivateKey):
        signature = private_key.sign(signed_attrs.dump(), sign_parameter)
    else:  # pragma: no cover - guarded above
        raise PadesError("Algoritmo da chave privada não suportado.")

    signer_info = cms.SignerInfo(
        {
            "version": "v1",
            "sid": cms.SignerIdentifier(
                {
                    "issuer_and_serial_number": cms.IssuerAndSerialNumber(
                        {"issuer": leaf.issuer, "serial_number": leaf.serial_number}
                    )
                }
            ),
            "digest_algorithm": {"algorithm": "sha256"},
            "signed_attrs": signed_attrs,
            "signature_algorithm": {"algorithm": algorithm},
            "signature": signature,
        }
    )
    certs = [leaf]
    for item in chain or []:
        certs.append(asn1_x509.Certificate.load(item.public_bytes(serialization.Encoding.DER)))
    signed_data = cms.SignedData(
        {
            "version": "v1",
            "digest_algorithms": [{"algorithm": "sha256"}],
            "encap_content_info": {"content_type": "data"},
            "certificates": certs,
            "signer_infos": [signer_info],
        }
    )
    return cms.ContentInfo({"content_type": "signed_data", "content": signed_data}).dump()


def embed_cms(prepared: PreparedPadesRevision, cms_der: bytes) -> bytes:
    cms_hex = cms_der.hex().upper().encode("ascii")
    if len(cms_hex) > prepared.contents_hex_length:
        raise PadesError(
            f"Assinatura CMS ({len(cms_der)} bytes) excede a reserva de {prepared.contents_hex_length // 2} bytes."
        )
    output = bytearray(prepared.pdf)
    padded = cms_hex + (b"0" * (prepared.contents_hex_length - len(cms_hex)))
    start = prepared.contents_hex_offset
    output[start : start + prepared.contents_hex_length] = padded
    return bytes(output)


def _find_signer_certificate(signed_data: cms.SignedData, signer_info: cms.SignerInfo) -> x509.Certificate:
    sid = signer_info["sid"]
    if sid.name != "issuer_and_serial_number":
        raise PadesError("SignerIdentifier CMS não usa issuer/serial.")
    serial = int(sid.chosen["serial_number"].native)
    issuer = sid.chosen["issuer"].dump()
    for choice in signed_data["certificates"] or []:
        if choice.name != "certificate":
            continue
        cert = choice.chosen
        if int(cert.serial_number) == serial and cert.issuer.dump() == issuer:
            return x509.load_der_x509_certificate(cert.dump())
    raise PadesError("Certificado do signatário não foi encontrado no CMS.")


def validate_cades_for_content(cms_der: bytes, content: bytes) -> dict[str, Any]:
    try:
        info = cms.ContentInfo.load(cms_der)
    except Exception as exc:
        raise PadesError("CMS embutido não pôde ser decodificado.") from exc
    if info["content_type"].native != "signed_data":
        raise PadesError("Conteúdo CMS não é SignedData.")
    signed_data = info["content"]
    if signed_data["encap_content_info"]["content"].native is not None:
        raise PadesError("CMS PAdES deve ser detached; conteúdo encapsulado inesperado.")
    signers = signed_data["signer_infos"]
    if len(signers) != 1:
        raise PadesError("Cada campo PAdES deve conter exatamente um SignerInfo.")
    signer = signers[0]
    attrs = signer["signed_attrs"]
    digest_attrs = [item for item in attrs if item["type"].native == "message_digest"]
    if len(digest_attrs) != 1:
        raise PadesError("CMS não contém messageDigest único.")
    expected_digest = hashlib.sha256(content).digest()
    if digest_attrs[0]["values"][0].native != expected_digest:
        raise PadesError("messageDigest do CMS diverge do ByteRange assinado.")
    signing_cert_attrs = [item for item in attrs if item["type"].native == "signing_certificate_v2"]
    if len(signing_cert_attrs) != 1:
        raise PadesError("CMS não contém SigningCertificateV2 exigido pelo perfil PAdES baseline.")

    cert = _find_signer_certificate(signed_data, signer)
    cert_hash = hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).digest()
    ess = signing_cert_attrs[0]["values"][0]["certs"][0]
    if ess["cert_hash"].native != cert_hash:
        raise PadesError("SigningCertificateV2 não referencia o certificado assinante.")

    public_key = cert.public_key()
    signature = signer["signature"].native
    # RFC 5652 assina a codificação DER do SET OF (tag universal 0x31), não a tag implícita [0] usada dentro de SignerInfo.
    signed_attrs_der = attrs.untag().dump()
    try:
        if isinstance(public_key, rsa.RSAPublicKey):
            public_key.verify(signature, signed_attrs_der, padding.PKCS1v15(), hashes.SHA256())
        elif isinstance(public_key, ec.EllipticCurvePublicKey):
            public_key.verify(signature, signed_attrs_der, ec.ECDSA(hashes.SHA256()))
        elif isinstance(public_key, dsa.DSAPublicKey):
            public_key.verify(signature, signed_attrs_der, hashes.SHA256())
        else:
            raise PadesError("Algoritmo de chave pública CMS não suportado.")
    except PadesError:
        raise
    except Exception as exc:
        raise PadesError("Assinatura criptográfica CMS inválida.") from exc
    return {
        "valid": True,
        "certificate_subject": cert.subject.rfc4514_string(),
        "certificate_serial": format(cert.serial_number, "x"),
        "message_digest_sha256": expected_digest.hex(),
        "signing_certificate_v2": True,
    }


def embed_validated_external_cades(prepared: PreparedPadesRevision, cms_der: bytes) -> tuple[bytes, dict[str, Any]]:
    validation = validate_cades_for_content(cms_der, prepared.signed_content)
    output = embed_cms(prepared, cms_der)
    # Reabre o PDF final para provar que o campo/ByteRange persistiu corretamente.
    matches = extract_pades_signatures(output)
    current = next((item for item in matches if item.get("field_name") == prepared.field_name), None)
    if current is None or not current.get("valid"):
        raise PadesError("CMS externo foi embutido, mas a revisão PDF final não revalidou.")
    return output, validation


def extract_pades_signatures(pdf: bytes) -> list[dict[str, Any]]:
    try:
        reader = PdfReader(io.BytesIO(pdf), strict=False)
    except Exception as exc:
        raise PadesError("PDF assinado não pôde ser analisado.") from exc
    fields = reader.get_fields() or {}
    results: list[dict[str, Any]] = []
    for name, field in fields.items():
        if field.get("/FT") != "/Sig" or field.get("/V") is None:
            continue
        sig = field["/V"]
        if isinstance(sig, IndirectObject):
            sig = sig.get_object()
        byte_range = [int(value) for value in sig.get("/ByteRange", [])]
        if len(byte_range) != 4 or byte_range[0] != 0:
            raise PadesError(f"ByteRange inválido no campo {name}.")
        contents = sig.get("/Contents")
        if contents is None:
            raise PadesError(f"Contents ausente no campo {name}.")
        # ByteStringObject converte automaticamente hexadecimal para bytes, incluindo padding zero.
        cms_bytes = bytes(contents)
        # ASN.1 informa o tamanho real; ignore zero padding da reserva PDF.
        try:
            parsed = cms.ContentInfo.load(cms_bytes)
            cms_der = parsed.dump()
        except Exception as exc:
            raise PadesError(f"CMS inválido no campo {name}.") from exc
        signed_content = pdf[: byte_range[1]] + pdf[byte_range[2] : byte_range[2] + byte_range[3]]
        validation = validate_cades_for_content(cms_der, signed_content)
        results.append({"field_name": str(name), "byte_range": byte_range, "cms_der": cms_der, **validation})
    return results


def sign_pades_b_b(
    pdf: bytes,
    *,
    certificate: x509.Certificate,
    private_key: Any,
    chain: list[x509.Certificate] | tuple[x509.Certificate, ...] | None = None,
    field_name: str,
    signer_name: str | None = None,
    reason: str | None = None,
    placeholder_bytes: int = 65536,
) -> PadesSignatureResult:
    prepared = prepare_incremental_signature(
        pdf,
        field_name=field_name,
        signer_name=signer_name,
        reason=reason,
        placeholder_bytes=placeholder_bytes,
    )
    cms_der = build_cades_bes(
        prepared.signed_content,
        certificate=certificate,
        private_key=private_key,
        chain=chain,
    )
    output = embed_cms(prepared, cms_der)
    signatures = extract_pades_signatures(output)
    current = next((item for item in signatures if item["field_name"] == field_name), None)
    if current is None or not current.get("valid"):
        raise PadesError("A assinatura PAdES embutida não pôde ser revalidada após a escrita.")
    return PadesSignatureResult(
        pdf=output,
        cms_der=cms_der,
        byte_range=prepared.byte_range,
        field_name=field_name,
        profile="PAdES-B-B",
        input_sha256=hashlib.sha256(pdf).hexdigest(),
        output_sha256=hashlib.sha256(output).hexdigest(),
        signed_content_sha256=hashlib.sha256(prepared.signed_content).hexdigest(),
    )
