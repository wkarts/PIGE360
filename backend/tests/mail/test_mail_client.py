from __future__ import annotations

import json


class MailFakeTransport:
    def __init__(self):
        self.sent: list[dict] = []
        self.fetches: list[tuple[str, int]] = []
        self.seen_updates: list[tuple[str, int, bool]] = []
        self.moves: list[tuple[str, int, str]] = []

    def mail_health(self, config, username):
        return {"ok": True, "imap": True, "smtp": True, "username": username}

    def mail_list_folders(self, config, username):
        return [
            {"remote_name": "INBOX", "display_name": "Entrada", "special_use": "\\Inbox"},
            {"remote_name": "Sent", "display_name": "Enviados", "special_use": "\\Sent"},
            {"remote_name": "Trash", "display_name": "Lixeira", "special_use": "\\Trash"},
        ]

    def mail_fetch_metadata(self, config, username, folder, uid_after, limit):
        if folder != "INBOX":
            return []
        source = [
            {
                "remote_uid": 10,
                "message_id": "<m10@example.com>",
                "in_reply_to": None,
                "subject": "Bem-vindo ao PIGE360",
                "sender": {"name": "Secretaria", "email": "secretaria@example.com"},
                "recipients": [{"name": "", "email": username}],
                "cc": [], "bcc": [],
                "sent_at": "2026-08-08T10:00:00+00:00",
                "received_at": "2026-08-08T10:00:00+00:00",
                "flags": ["\\Seen"], "size_bytes": 500, "has_attachments": False,
                "preview": "Mensagem inicial", "content_sha256": "a" * 64,
            },
            {
                "remote_uid": 11,
                "message_id": "<m11@example.com>",
                "in_reply_to": "<m10@example.com>",
                "subject": "Re: Bem-vindo ao PIGE360",
                "sender": {"name": "Direção", "email": "direcao@example.com"},
                "recipients": [{"name": "", "email": username}],
                "cc": [], "bcc": [],
                "sent_at": "2026-08-08T10:05:00+00:00",
                "received_at": "2026-08-08T10:05:00+00:00",
                "flags": [], "size_bytes": 700, "has_attachments": True,
                "preview": "Resposta com anexo", "content_sha256": "b" * 64,
            },
        ]
        return [row for row in source if row["remote_uid"] > uid_after][:limit]

    def mail_fetch_message(self, config, username, folder, uid):
        self.fetches.append((folder, uid))
        return {
            "remote_uid": uid,
            "message_id": f"<m{uid}@example.com>",
            "subject": "Conteúdo sob demanda",
            "sender": {"name": "Direção", "email": "direcao@example.com"},
            "recipients": [{"name": "", "email": username}],
            "cc": [],
            "sent_at": "2026-08-08T10:05:00+00:00",
            "text": "Corpo oficial buscado no IMAP.",
            "html": None,
            "attachments": [{"filename": "arquivo.pdf", "content_type": "application/pdf", "size_bytes": 20, "sha256": "c" * 64}],
            "content_sha256": "f" * 64,
        }


    def mail_set_seen(self, config, username, folder, uid, seen):
        self.seen_updates.append((folder, uid, seen))
        return {"remote_uid": uid, "seen": seen}

    def mail_move_message(self, config, username, folder, uid, destination):
        self.moves.append((folder, uid, destination))
        return {"remote_uid": uid, "destination": destination, "moved": True}

    def mail_fetch_attachment(self, config, username, folder, uid, attachment_index):
        assert attachment_index == 0
        return {
            "filename": "arquivo.pdf",
            "content_type": "application/pdf",
            "content": b"%PDF-1.7\nPIGE360 attachment fixture\n%%EOF",
        }

    def mail_send(self, config, username, payload):
        self.sent.append(payload)
        return {"message_id": f"<sent-{len(self.sent)}@example.com>", "accepted": True}


def _secret(local_env, name: str, value: dict):
    root = local_env.root / "integration-secrets"
    root.mkdir(parents=True, exist_ok=True)
    (root / name).write_text(json.dumps(value), encoding="utf-8")


def _setup_mail(local_env):
    fake = MailFakeTransport()
    local_env.client.app.state.integration_transport = fake
    _secret(local_env, "mail-connection", {"unused": "api-placeholder"})
    _secret(local_env, "mail-owner", {"username": "owner@alpha.example.com", "password": "App-Password-Local-2026!"})
    connection = local_env.client.post(
        "/api/v1/integration-connections",
        headers=local_env.alpha_headers(),
        json={
            "provider": "generic_imap_smtp",
            "name": "E-mail institucional",
            "environment": "production",
            "capabilities": ["imap", "smtp"],
            "secret_reference": "mail-connection",
            "config": {"imap_host": "imap.example.com", "smtp_host": "smtp.example.com", "smtp_tls": "starttls"},
        },
    )
    assert connection.status_code == 201, connection.text
    account = local_env.client.post(
        "/api/v1/mail/accounts",
        headers=local_env.alpha_headers(),
        json={
            "user_id": local_env.alpha_tenant["owner"]["id"],
            "email": "owner@alpha.example.com",
            "display_name": "Responsável Alpha",
            "provider_connection_id": connection.json()["id"],
            "credential_secret_reference": "mail-owner",
            "mode": "generic_imap_smtp",
            "quota_mb": 2048,
        },
    )
    assert account.status_code == 201, account.text
    return fake, account.json()


def test_mail_sync_read_send_draft_and_no_body_persistence(local_env):
    fake, account = _setup_mail(local_env)

    health = local_env.client.post("/api/v1/mail/me/health", headers=local_env.alpha_headers())
    assert health.status_code == 200, health.text
    assert health.json()["status"] == "healthy"

    first = local_env.client.post("/api/v1/mail/me/sync", headers=local_env.alpha_headers())
    assert first.status_code == 200, first.text
    assert first.json()["folders_synced"] == 3
    assert first.json()["messages_synced"] == 2
    second = local_env.client.post("/api/v1/mail/me/sync", headers=local_env.alpha_headers())
    assert second.status_code == 200, second.text
    assert second.json()["messages_synced"] == 0

    inbox = local_env.client.get("/api/v1/mail/me/messages", headers=local_env.alpha_headers(), params={"folder": "INBOX"})
    assert inbox.status_code == 200, inbox.text
    assert len(inbox.json()["items"]) == 2
    assert inbox.json()["items"][0]["remote_uid"] == 11
    assert inbox.json()["items"][0]["has_attachments"] == 1
    message_id = inbox.json()["items"][0]["id"]

    detail = local_env.client.get(f"/api/v1/mail/me/messages/{message_id}", headers=local_env.alpha_headers())
    assert detail.status_code == 200, detail.text
    assert detail.json()["content"]["text"] == "Corpo oficial buscado no IMAP."
    assert fake.fetches == [("INBOX", 11)]

    # PostgreSQL/SQLite guardam somente metadata; o corpo oficial não é persistido.
    store = local_env.client.app.state.data_router.tenant_store(local_env.alpha_tenant["id"])
    columns = {row["name"] for row in store.fetch_all("PRAGMA table_info(mail_message_metadata)")}
    assert "body_text" not in columns and "body_html" not in columns

    send = local_env.client.post(
        "/api/v1/mail/me/send",
        headers={**local_env.alpha_headers(), "Idempotency-Key": "mail-send-0001"},
        json={"to": ["destino@example.com"], "subject": "Teste", "body_text": "Conteúdo"},
    )
    replay = local_env.client.post(
        "/api/v1/mail/me/send",
        headers={**local_env.alpha_headers(), "Idempotency-Key": "mail-send-0001"},
        json={"to": ["destino@example.com"], "subject": "Teste", "body_text": "Conteúdo"},
    )
    assert send.status_code == 201 and replay.status_code == 201
    assert send.json() == replay.json()
    assert len(fake.sent) == 1

    # Operações de mailbox usam o provider oficial e mantêm metadata local coerente.
    unread = local_env.client.post(
        f"/api/v1/mail/me/messages/{message_id}/seen",
        headers=local_env.alpha_headers(),
        json={"seen": True},
    )
    assert unread.status_code == 200, unread.text
    assert unread.json()["seen"] is True
    assert fake.seen_updates == [("INBOX", 11, True)]

    reply = local_env.client.post(
        f"/api/v1/mail/me/messages/{message_id}/reply",
        headers={**local_env.alpha_headers(), "Idempotency-Key": "mail-reply-0001"},
        json={"body_text": "Resposta institucional", "reply_all": True},
    )
    assert reply.status_code == 201, reply.text
    assert fake.sent[-1]["in_reply_to"] == "<m11@example.com>"

    forward = local_env.client.post(
        f"/api/v1/mail/me/messages/{message_id}/forward",
        headers={**local_env.alpha_headers(), "Idempotency-Key": "mail-forward-0001"},
        json={"to": ["auditoria@example.com"], "subject": "", "body_text": "Encaminhado para auditoria"},
    )
    assert forward.status_code == 201, forward.text
    assert fake.sent[-1]["subject"].startswith("Fwd:")

    attachment = local_env.client.get(
        f"/api/v1/mail/me/messages/{message_id}/attachments/0",
        headers=local_env.alpha_headers(),
    )
    assert attachment.status_code == 200, attachment.text
    assert attachment.content.startswith(b"%PDF-1.7")
    assert len(attachment.headers["x-content-sha256"]) == 64

    trashed = local_env.client.post(
        f"/api/v1/mail/me/messages/{message_id}/trash",
        headers=local_env.alpha_headers(),
    )
    assert trashed.status_code == 200, trashed.text
    assert trashed.json()["folder"] == "Trash"
    assert fake.moves == [("INBOX", 11, "Trash")]
    gone = local_env.client.get(f"/api/v1/mail/me/messages/{message_id}", headers=local_env.alpha_headers())
    assert gone.status_code == 404

    draft = local_env.client.post(
        "/api/v1/mail/me/drafts",
        headers=local_env.alpha_headers(),
        json={"to": ["draft@example.com"], "subject": "Rascunho", "body_text": "Versão 1"},
    )
    assert draft.status_code == 201, draft.text
    updated = local_env.client.patch(
        f"/api/v1/mail/me/drafts/{draft.json()['id']}",
        headers=local_env.alpha_headers(),
        json={"expected_version": 1, "to": ["draft@example.com"], "subject": "Rascunho", "body_text": "Versão 2"},
    )
    assert updated.status_code == 200 and updated.json()["version"] == 2
    sent_draft = local_env.client.post(
        f"/api/v1/mail/me/drafts/{draft.json()['id']}/send",
        headers={**local_env.alpha_headers(), "Idempotency-Key": "draft-send-0001"},
    )
    assert sent_draft.status_code == 200, sent_draft.text
    assert sent_draft.json()["state"] == "sent"
    assert len(fake.sent) == 4


def test_mail_delegation_is_read_only_and_cross_tenant_isolated(local_env):
    fake, account = _setup_mail(local_env)
    sync = local_env.client.post("/api/v1/mail/me/sync", headers=local_env.alpha_headers())
    assert sync.status_code == 200

    delegate, delegate_token = local_env.create_alpha_user("delegate@alpha.example.com", ["employee"])
    delegated = local_env.client.post(
        f"/api/v1/mail/accounts/{account['id']}/delegations",
        headers=local_env.alpha_headers(),
        json={"delegate_user_id": delegate["id"], "can_read": True, "can_send": False},
    )
    assert delegated.status_code == 201, delegated.text
    delegate_headers = local_env.headers("admin.alpha.school.local", delegate_token)
    listing = local_env.client.get("/api/v1/mail/me/messages", headers=delegate_headers)
    assert listing.status_code == 200 and len(listing.json()["items"]) == 2
    denied = local_env.client.post(
        "/api/v1/mail/me/send",
        headers={**delegate_headers, "Idempotency-Key": "delegate-mail-1"},
        json={"to": ["destino@example.com"], "subject": "Não permitido", "body_text": "x"},
    )
    assert denied.status_code == 403
    assert len(fake.sent) == 0

    listed = local_env.client.get(
        f"/api/v1/mail/accounts/{account['id']}/delegations", headers=local_env.alpha_headers()
    )
    assert listed.status_code == 200 and len(listed.json()["items"]) == 1
    revoked = local_env.client.post(
        f"/api/v1/mail/accounts/{account['id']}/delegations/{delegated.json()['id']}/revoke",
        headers=local_env.alpha_headers(),
    )
    assert revoked.status_code == 200 and revoked.json()["state"] == "revoked"
    denied_after_revoke = local_env.client.get("/api/v1/mail/me/messages", headers=delegate_headers)
    assert denied_after_revoke.status_code == 403

    # Outro tenant não possui/descobre a mailbox Alpha.
    beta = local_env.client.get("/api/v1/mail/me/status", headers=local_env.beta_headers())
    assert beta.status_code == 403
