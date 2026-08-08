"""Mail account, sync metadata, drafts and delegations.

Revision ID: 0011_mail_metadata
Revises: 0010_ibpt_catalogs
"""
from alembic import op

revision = "0011_mail_metadata"
down_revision = "0010_ibpt_catalogs"
branch_labels = None
depends_on = None

TABLES = ("mail_accounts", "mail_folders", "mail_message_metadata", "mail_drafts", "mail_sync_runs", "mail_delegations")


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS mail_accounts (
      id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, user_id TEXT NOT NULL, person_id TEXT,
      email TEXT NOT NULL, display_name TEXT, provider_connection_id TEXT NOT NULL REFERENCES integration_connections(id),
      credential_secret_reference TEXT, mode TEXT NOT NULL DEFAULT 'generic_imap_smtp', state TEXT NOT NULL DEFAULT 'active',
      quota_mb INTEGER, last_sync_at TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
      UNIQUE(tenant_id,email), UNIQUE(tenant_id,user_id)
    );
    CREATE TABLE IF NOT EXISTS mail_folders (
      id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, account_id TEXT NOT NULL REFERENCES mail_accounts(id), remote_name TEXT NOT NULL,
      display_name TEXT NOT NULL, special_use TEXT, uid_validity TEXT, highest_uid INTEGER NOT NULL DEFAULT 0,
      unread_count INTEGER NOT NULL DEFAULT 0, total_count INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
      UNIQUE(tenant_id,account_id,remote_name)
    );
    CREATE TABLE IF NOT EXISTS mail_message_metadata (
      id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, account_id TEXT NOT NULL REFERENCES mail_accounts(id), folder_id TEXT NOT NULL REFERENCES mail_folders(id),
      remote_uid BIGINT NOT NULL, message_id TEXT, thread_key TEXT, in_reply_to TEXT, subject TEXT,
      sender_json TEXT NOT NULL DEFAULT '{}', recipients_json TEXT NOT NULL DEFAULT '[]', cc_json TEXT NOT NULL DEFAULT '[]', bcc_json TEXT NOT NULL DEFAULT '[]',
      sent_at TEXT, received_at TEXT, flags_json TEXT NOT NULL DEFAULT '[]', size_bytes BIGINT, has_attachments BOOLEAN NOT NULL DEFAULT FALSE,
      preview TEXT, content_sha256 TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
      UNIQUE(tenant_id,account_id,folder_id,remote_uid)
    );
    CREATE INDEX IF NOT EXISTS idx_mail_message_account_received ON mail_message_metadata(tenant_id,account_id,received_at);
    CREATE TABLE IF NOT EXISTS mail_drafts (
      id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, account_id TEXT NOT NULL REFERENCES mail_accounts(id), subject TEXT,
      to_json TEXT NOT NULL DEFAULT '[]', cc_json TEXT NOT NULL DEFAULT '[]', bcc_json TEXT NOT NULL DEFAULT '[]', body_text TEXT NOT NULL DEFAULT '',
      body_html TEXT, attachments_json TEXT NOT NULL DEFAULT '[]', state TEXT NOT NULL DEFAULT 'draft', provider_message_id TEXT,
      version INTEGER NOT NULL DEFAULT 1, created_by TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS mail_sync_runs (
      id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, account_id TEXT NOT NULL REFERENCES mail_accounts(id), state TEXT NOT NULL,
      folders_synced INTEGER NOT NULL DEFAULT 0, messages_synced INTEGER NOT NULL DEFAULT 0,
      error_code TEXT, error_message TEXT, started_at TEXT NOT NULL, finished_at TEXT
    );
    CREATE TABLE IF NOT EXISTS mail_delegations (
      id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, account_id TEXT NOT NULL REFERENCES mail_accounts(id), delegate_user_id TEXT NOT NULL,
      can_read BOOLEAN NOT NULL DEFAULT TRUE, can_send BOOLEAN NOT NULL DEFAULT FALSE, valid_from TEXT, valid_until TEXT,
      state TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
      UNIQUE(tenant_id,account_id,delegate_user_id)
    );
    """)
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")
        op.execute(
            f"CREATE POLICY {table}_tenant_isolation ON {table} "
            "USING (tenant_id = current_setting('app.tenant_id', true)) "
            "WITH CHECK (tenant_id = current_setting('app.tenant_id', true))"
        )


def downgrade() -> None:
    for table in reversed(TABLES):
        op.execute(f"DROP TABLE IF EXISTS {table}")
