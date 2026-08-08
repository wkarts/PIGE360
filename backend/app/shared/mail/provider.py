from __future__ import annotations

import email
import hashlib
import imaplib
import ipaddress
import json
import re
import smtplib
import socket
import ssl
import time
from dataclasses import dataclass
from email import policy
from email.header import decode_header, make_header
from email.message import EmailMessage, Message
from email.parser import BytesParser
from email.utils import getaddresses, parsedate_to_datetime
from typing import Any

from app.shared.integrations.providers import IntegrationError


@dataclass(frozen=True, slots=True)
class MailHealth:
    status: str
    latency_ms: int
    details: dict[str, Any]


def _secret_json(secret: str) -> tuple[str, str]:
    try:
        data = json.loads(secret)
    except json.JSONDecodeError as exc:
        raise IntegrationError("MAIL_SECRET_INVALID", "Credencial IMAP/SMTP deve ser JSON.") from exc
    if not isinstance(data, dict):
        raise IntegrationError("MAIL_SECRET_INVALID", "Credencial IMAP/SMTP deve ser objeto JSON.")
    username = str(data.get("username") or "").strip()
    password = str(data.get("password") or "")
    if not username or not password:
        raise IntegrationError("MAIL_CREDENTIALS_MISSING", "username/password não configurados para a mailbox.")
    return username, password


def _safe_host(host: str, port: int, *, allow_private_network: bool) -> None:
    host = host.strip().rstrip(".").lower()
    if not host or port < 1 or port > 65535:
        raise IntegrationError("MAIL_HOST_INVALID", "Host/porta de e-mail inválidos.")
    if allow_private_network:
        return
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".localhost"):
        raise IntegrationError("INTEGRATION_SSRF_BLOCKED", "Servidor de e-mail local bloqueado pela política de SSRF.")
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        if literal.is_private or literal.is_loopback or literal.is_link_local or literal.is_reserved or literal.is_unspecified or literal.is_multicast:
            raise IntegrationError("INTEGRATION_SSRF_BLOCKED", "Servidor de e-mail privado/reservado bloqueado.")
        return
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise IntegrationError("MAIL_DNS_ERROR", "Não foi possível resolver o servidor de e-mail.", retryable=True) from exc
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if address.is_private or address.is_loopback or address.is_link_local or address.is_reserved or address.is_unspecified or address.is_multicast:
            raise IntegrationError("INTEGRATION_SSRF_BLOCKED", "Servidor de e-mail resolveu para endereço privado/reservado.")


def _decode(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def _addresses(value: str | None) -> list[dict[str, str]]:
    return [{"name": _decode(name), "email": addr.lower()} for name, addr in getaddresses([value or ""]) if addr]


def _date(value: str | None) -> str | None:
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
        if dt is None:
            return None
        if dt.tzinfo is None:
            from datetime import UTC
            dt = dt.replace(tzinfo=UTC)
        return dt.isoformat()
    except Exception:
        return None


def _plain_preview(message: Message, limit: int = 400) -> str:
    candidates: list[str] = []
    if message.is_multipart():
        for part in message.walk():
            if part.get_content_maintype() == "multipart" or part.get_filename():
                continue
            if part.get_content_type() == "text/plain":
                try:
                    candidates.append(part.get_content())
                except Exception:
                    pass
    elif message.get_content_type() == "text/plain":
        try:
            candidates.append(message.get_content())
        except Exception:
            pass
    text = re.sub(r"\s+", " ", " ".join(candidates)).strip()
    return text[:limit]


def _body(message: Message) -> dict[str, Any]:
    text = ""
    html = ""
    attachments: list[dict[str, Any]] = []
    parts = message.walk() if message.is_multipart() else [message]
    for part in parts:
        if part.get_content_maintype() == "multipart":
            continue
        filename = _decode(part.get_filename()) if part.get_filename() else ""
        content_type = part.get_content_type()
        payload = part.get_payload(decode=True) or b""
        if filename:
            attachments.append({
                "filename": filename,
                "content_type": content_type,
                "size_bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            })
            continue
        try:
            content = part.get_content()
        except Exception:
            charset = part.get_content_charset() or "utf-8"
            content = payload.decode(charset, errors="replace")
        if content_type == "text/plain" and not text:
            text = str(content)
        elif content_type == "text/html" and not html:
            html = str(content)
    return {"text": text, "html": html or None, "attachments": attachments}


class ImapSmtpMailProvider:
    provider_name = "generic_imap_smtp"

    def __init__(self, *, config: dict[str, Any], secret: str, transport: Any | None = None):
        self.config = dict(config)
        self.username, self.password = _secret_json(secret)
        self.imap_host = str(config.get("imap_host") or "").strip()
        self.imap_port = int(config.get("imap_port") or 993)
        self.smtp_host = str(config.get("smtp_host") or "").strip()
        self.smtp_port = int(config.get("smtp_port") or 587)
        self.smtp_tls = str(config.get("smtp_tls") or "starttls").lower()
        self.allow_private = bool(config.get("allow_private_network", False))
        self.timeout = float(config.get("timeout_seconds") or 20)
        self.transport = transport
        if not self.imap_host or not self.smtp_host or self.smtp_tls not in {"starttls", "ssl"}:
            raise IntegrationError("MAIL_CONFIG_INVALID", "imap_host, smtp_host e smtp_tls válidos são obrigatórios.")

    def _fake(self, method: str):
        fn = getattr(self.transport, method, None) if self.transport is not None else None
        return fn

    def _imap(self):
        if self.transport is not None and not self._fake("mail_list_folders"):
            raise IntegrationError("INTEGRATION_REMOTE_DISABLED", "IMAP externo desabilitado neste runtime.")
        _safe_host(self.imap_host, self.imap_port, allow_private_network=self.allow_private)
        try:
            client = imaplib.IMAP4_SSL(self.imap_host, self.imap_port, ssl_context=ssl.create_default_context(), timeout=self.timeout)
            client.login(self.username, self.password)
            return client
        except (OSError, imaplib.IMAP4.error) as exc:
            raise IntegrationError("MAIL_IMAP_CONNECTION_FAILED", "Falha ao conectar/autenticar no IMAP.", retryable=True) from exc

    def _smtp(self):
        if self.transport is not None and not self._fake("mail_send"):
            raise IntegrationError("INTEGRATION_REMOTE_DISABLED", "SMTP externo desabilitado neste runtime.")
        _safe_host(self.smtp_host, self.smtp_port, allow_private_network=self.allow_private)
        context = ssl.create_default_context()
        try:
            if self.smtp_tls == "ssl":
                client = smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, timeout=self.timeout, context=context)
            else:
                client = smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=self.timeout)
                client.ehlo(); client.starttls(context=context); client.ehlo()
            client.login(self.username, self.password)
            return client
        except (OSError, smtplib.SMTPException) as exc:
            raise IntegrationError("MAIL_SMTP_CONNECTION_FAILED", "Falha ao conectar/autenticar no SMTP.", retryable=True) from exc

    def health(self) -> MailHealth:
        started = time.perf_counter()
        fake = self._fake("mail_health")
        if fake:
            result = fake(self.config, self.username)
            ok = bool(result.get("ok", False))
            return MailHealth("healthy" if ok else "degraded", round((time.perf_counter()-started)*1000), dict(result))
        client = self._imap()
        try:
            status, _ = client.noop()
            ok = status == "OK"
        finally:
            try: client.logout()
            except Exception: pass
        return MailHealth("healthy" if ok else "degraded", round((time.perf_counter()-started)*1000), {"imap": ok})

    def list_folders(self) -> list[dict[str, Any]]:
        fake = self._fake("mail_list_folders")
        if fake:
            return list(fake(self.config, self.username))
        client = self._imap()
        try:
            status, rows = client.list()
            if status != "OK":
                raise IntegrationError("MAIL_IMAP_LIST_FAILED", "IMAP não retornou pastas.", retryable=True)
            result = []
            for raw in rows or []:
                line = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
                match = re.match(r'^\((.*?)\)\s+"([^"]*)"\s+(.+)$', line)
                if not match:
                    continue
                flags, _, name = match.groups(); name = name.strip().strip('"')
                special = next((flag for flag in flags.split() if flag.startswith("\\")), None)
                result.append({"remote_name": name, "display_name": name, "special_use": special})
            return result
        finally:
            try: client.logout()
            except Exception: pass

    def fetch_metadata(self, *, folder: str, uid_after: int = 0, limit: int = 200) -> list[dict[str, Any]]:
        fake = self._fake("mail_fetch_metadata")
        if fake:
            return list(fake(self.config, self.username, folder, uid_after, limit))
        client = self._imap()
        try:
            status, _ = client.select(f'"{folder}"', readonly=True)
            if status != "OK":
                raise IntegrationError("MAIL_IMAP_SELECT_FAILED", "Não foi possível abrir a pasta IMAP.")
            query = f"UID {max(1, uid_after + 1)}:*"
            status, data = client.uid("search", None, query)
            if status != "OK":
                raise IntegrationError("MAIL_IMAP_SEARCH_FAILED", "Falha ao consultar mensagens IMAP.", retryable=True)
            uids = [int(x) for x in (data[0] or b"").split() if x]
            uids = uids[-max(1, min(limit, 1000)):]
            result: list[dict[str, Any]] = []
            for uid in uids:
                status, response = client.uid("fetch", str(uid), "(BODY.PEEK[HEADER] FLAGS RFC822.SIZE)")
                if status != "OK" or not response:
                    continue
                blob = next((item[1] for item in response if isinstance(item, tuple) and len(item) > 1), b"")
                msg = BytesParser(policy=policy.default).parsebytes(blob)
                flags_line = " ".join(str(item[0]) for item in response if isinstance(item, tuple))
                flags = re.findall(r"\\[A-Za-z]+", flags_line)
                size_match = re.search(r"RFC822\.SIZE\s+(\d+)", flags_line)
                body = _body(msg)
                result.append({
                    "remote_uid": uid,
                    "message_id": str(msg.get("Message-ID") or "").strip() or None,
                    "in_reply_to": str(msg.get("In-Reply-To") or "").strip() or None,
                    "subject": _decode(msg.get("Subject")),
                    "sender": (_addresses(msg.get("From")) or [{}])[0],
                    "recipients": _addresses(msg.get("To")),
                    "cc": _addresses(msg.get("Cc")),
                    "bcc": [],
                    "sent_at": _date(msg.get("Date")),
                    "received_at": _date(msg.get("Date")),
                    "flags": flags,
                    "size_bytes": int(size_match.group(1)) if size_match else None,
                    "has_attachments": bool(body["attachments"]),
                    "preview": _plain_preview(msg),
                    "content_sha256": hashlib.sha256(blob).hexdigest(),
                })
            return result
        finally:
            try: client.logout()
            except Exception: pass

    def fetch_message(self, *, folder: str, uid: int) -> dict[str, Any]:
        fake = self._fake("mail_fetch_message")
        if fake:
            return dict(fake(self.config, self.username, folder, uid))
        client = self._imap()
        try:
            status, _ = client.select(f'"{folder}"', readonly=True)
            if status != "OK":
                raise IntegrationError("MAIL_IMAP_SELECT_FAILED", "Não foi possível abrir a pasta IMAP.")
            status, response = client.uid("fetch", str(uid), "(BODY.PEEK[])")
            if status != "OK" or not response:
                raise IntegrationError("MAIL_MESSAGE_NOT_FOUND", "Mensagem não localizada no IMAP.")
            blob = next((item[1] for item in response if isinstance(item, tuple) and len(item) > 1), None)
            if not blob:
                raise IntegrationError("MAIL_MESSAGE_NOT_FOUND", "Mensagem não localizada no IMAP.")
            msg = BytesParser(policy=policy.default).parsebytes(blob)
            return {
                "remote_uid": uid,
                "message_id": str(msg.get("Message-ID") or "").strip() or None,
                "subject": _decode(msg.get("Subject")),
                "sender": (_addresses(msg.get("From")) or [{}])[0],
                "recipients": _addresses(msg.get("To")),
                "cc": _addresses(msg.get("Cc")),
                "sent_at": _date(msg.get("Date")),
                **_body(msg),
                "content_sha256": hashlib.sha256(blob).hexdigest(),
            }
        finally:
            try: client.logout()
            except Exception: pass

    def set_seen(self, *, folder: str, uid: int, seen: bool) -> dict[str, Any]:
        fake = self._fake("mail_set_seen")
        if fake:
            return dict(fake(self.config, self.username, folder, uid, seen))
        client = self._imap()
        try:
            status, _ = client.select(f'"{folder}"', readonly=False)
            if status != "OK":
                raise IntegrationError("MAIL_IMAP_SELECT_FAILED", "Não foi possível abrir a pasta IMAP.")
            op = "+FLAGS.SILENT" if seen else "-FLAGS.SILENT"
            status, _ = client.uid("store", str(uid), op, "(\\Seen)")
            if status != "OK":
                raise IntegrationError("MAIL_IMAP_FLAG_FAILED", "Não foi possível atualizar a mensagem no IMAP.", retryable=True)
            return {"remote_uid": uid, "seen": seen}
        finally:
            try: client.logout()
            except Exception: pass

    def move_message(self, *, folder: str, uid: int, destination: str) -> dict[str, Any]:
        fake = self._fake("mail_move_message")
        if fake:
            return dict(fake(self.config, self.username, folder, uid, destination))
        client = self._imap()
        try:
            status, _ = client.select(f'"{folder}"', readonly=False)
            if status != "OK":
                raise IntegrationError("MAIL_IMAP_SELECT_FAILED", "Não foi possível abrir a pasta IMAP.")
            # RFC 6851 quando disponível; fallback COPY + \Deleted preserva compatibilidade.
            status, response = client.uid("MOVE", str(uid), f'"{destination}"')
            if status != "OK":
                status, _ = client.uid("COPY", str(uid), f'"{destination}"')
                if status != "OK":
                    raise IntegrationError("MAIL_IMAP_MOVE_FAILED", "Não foi possível mover a mensagem.", retryable=True)
                status, _ = client.uid("store", str(uid), "+FLAGS.SILENT", "(\\Deleted)")
                if status != "OK":
                    raise IntegrationError("MAIL_IMAP_MOVE_FAILED", "Não foi possível concluir a movimentação da mensagem.", retryable=True)
                client.expunge()
            return {"remote_uid": uid, "destination": destination, "moved": True, "provider_response": str(response or "")[:200]}
        finally:
            try: client.logout()
            except Exception: pass

    def fetch_attachment(self, *, folder: str, uid: int, attachment_index: int) -> dict[str, Any]:
        if attachment_index < 0 or attachment_index > 999:
            raise IntegrationError("MAIL_ATTACHMENT_INVALID", "Índice de anexo inválido.")
        fake = self._fake("mail_fetch_attachment")
        if fake:
            result = dict(fake(self.config, self.username, folder, uid, attachment_index))
            payload = result.get("content")
            if not isinstance(payload, (bytes, bytearray)):
                raise IntegrationError("MAIL_ATTACHMENT_INVALID", "Provider retornou anexo inválido.")
            result["content"] = bytes(payload)
            result["sha256"] = hashlib.sha256(result["content"]).hexdigest()
            return result
        client = self._imap()
        try:
            status, _ = client.select(f'"{folder}"', readonly=True)
            if status != "OK":
                raise IntegrationError("MAIL_IMAP_SELECT_FAILED", "Não foi possível abrir a pasta IMAP.")
            status, response = client.uid("fetch", str(uid), "(BODY.PEEK[])")
            if status != "OK" or not response:
                raise IntegrationError("MAIL_MESSAGE_NOT_FOUND", "Mensagem não localizada no IMAP.")
            blob = next((item[1] for item in response if isinstance(item, tuple) and len(item) > 1), None)
            if not blob:
                raise IntegrationError("MAIL_MESSAGE_NOT_FOUND", "Mensagem não localizada no IMAP.")
            msg = BytesParser(policy=policy.default).parsebytes(blob)
            current = -1
            for part in msg.walk() if msg.is_multipart() else [msg]:
                if not part.get_filename():
                    continue
                current += 1
                if current != attachment_index:
                    continue
                payload = part.get_payload(decode=True) or b""
                return {
                    "filename": _decode(part.get_filename()) or f"anexo-{attachment_index + 1}",
                    "content_type": part.get_content_type() or "application/octet-stream",
                    "content": payload,
                    "size_bytes": len(payload),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                }
            raise IntegrationError("MAIL_ATTACHMENT_NOT_FOUND", "Anexo não localizado nesta mensagem.")
        finally:
            try: client.logout()
            except Exception: pass

    def send_message(self, *, to: list[str], cc: list[str], bcc: list[str], subject: str, text: str, html: str | None = None, in_reply_to: str | None = None, references: str | None = None) -> dict[str, Any]:
        recipients = [x.strip().lower() for x in [*to, *cc, *bcc] if x.strip()]
        if not recipients or any("@" not in x for x in recipients):
            raise IntegrationError("MAIL_RECIPIENT_INVALID", "Informe destinatários de e-mail válidos.")
        payload = {"from": self.username, "to": to, "cc": cc, "bcc": bcc, "subject": subject, "text": text, "html": html, "in_reply_to": in_reply_to, "references": references}
        fake = self._fake("mail_send")
        if fake:
            return dict(fake(self.config, self.username, payload))
        msg = EmailMessage(policy=policy.SMTP)
        msg["From"] = self.username; msg["To"] = ", ".join(to); msg["Subject"] = subject
        if cc: msg["Cc"] = ", ".join(cc)
        if in_reply_to: msg["In-Reply-To"] = in_reply_to
        if references: msg["References"] = references
        msg.set_content(text or "")
        if html: msg.add_alternative(html, subtype="html")
        client = self._smtp()
        try:
            refused = client.send_message(msg, from_addr=self.username, to_addrs=recipients)
            if refused:
                raise IntegrationError("MAIL_RECIPIENT_REFUSED", "SMTP recusou destinatário(s).")
        finally:
            try: client.quit()
            except Exception: client.close()
        return {"message_id": msg.get("Message-ID"), "accepted": True}
