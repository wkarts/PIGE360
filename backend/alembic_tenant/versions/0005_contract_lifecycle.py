"""Ciclo completo de contratos e evidências de assinatura.

Revision ID: 0005_contract_lifecycle
Revises: 0004_integration_operation_keys
"""
from alembic import op

revision = "0005_contract_lifecycle"
down_revision = "0004_integration_operation_keys"
branch_labels = None
depends_on = None

TABLES = ["contract_versions","contract_amendments","contract_relationships","signature_otp_challenges","signature_attempts","signature_validations","signature_artifacts","signature_evidence_packages"]

def upgrade() -> None:
    op.execute("""CREATE TABLE IF NOT EXISTS contract_versions (id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,contract_id TEXT NOT NULL REFERENCES legal_contracts(id),version INTEGER NOT NULL,state TEXT NOT NULL,effective_from TEXT,effective_until TEXT,document_sha256 TEXT,document_storage_key TEXT,snapshot_id TEXT,reason TEXT,actor_id TEXT,created_at TEXT NOT NULL,UNIQUE(tenant_id,contract_id,version))""")
    op.execute("""CREATE TABLE IF NOT EXISTS contract_amendments (id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,contract_id TEXT NOT NULL REFERENCES legal_contracts(id),amendment_contract_id TEXT NOT NULL REFERENCES legal_contracts(id),amendment_type TEXT NOT NULL,title TEXT NOT NULL,payload_json TEXT NOT NULL DEFAULT '{}',effective_from TEXT,state TEXT NOT NULL DEFAULT 'draft',version INTEGER NOT NULL DEFAULT 1,created_by TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL)""")
    op.execute("""CREATE TABLE IF NOT EXISTS contract_relationships (id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,source_contract_id TEXT NOT NULL REFERENCES legal_contracts(id),target_contract_id TEXT NOT NULL REFERENCES legal_contracts(id),relationship_type TEXT NOT NULL,created_by TEXT NOT NULL,created_at TEXT NOT NULL,UNIQUE(tenant_id,source_contract_id,target_contract_id,relationship_type))""")
    op.execute("""CREATE TABLE IF NOT EXISTS signature_otp_challenges (id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,envelope_id TEXT NOT NULL REFERENCES signature_envelopes(id),signer_id TEXT NOT NULL,user_id TEXT NOT NULL,channel TEXT NOT NULL,destination_masked TEXT NOT NULL,expires_at TEXT NOT NULL,attempts INTEGER NOT NULL DEFAULT 0,max_attempts INTEGER NOT NULL DEFAULT 5,consumed_at TEXT,created_at TEXT NOT NULL)""")
    op.execute("""CREATE TABLE IF NOT EXISTS signature_attempts (id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,envelope_id TEXT NOT NULL REFERENCES signature_envelopes(id),signer_id TEXT,provider TEXT NOT NULL,action TEXT NOT NULL,state TEXT NOT NULL,request_json TEXT NOT NULL DEFAULT '{}',response_json TEXT NOT NULL DEFAULT '{}',error TEXT,correlation_id TEXT,created_at TEXT NOT NULL,finished_at TEXT)""")
    op.execute("""CREATE TABLE IF NOT EXISTS signature_validations (id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,envelope_id TEXT NOT NULL REFERENCES signature_envelopes(id),valid INTEGER NOT NULL,document_hash_valid INTEGER NOT NULL,evidence_valid INTEGER NOT NULL,details_json TEXT NOT NULL DEFAULT '{}',validated_by TEXT,created_at TEXT NOT NULL)""")
    op.execute("""CREATE TABLE IF NOT EXISTS signature_artifacts (id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,envelope_id TEXT NOT NULL REFERENCES signature_envelopes(id),signer_id TEXT NOT NULL,provider TEXT NOT NULL,artifact_type TEXT NOT NULL,sha256 TEXT NOT NULL,storage_key TEXT NOT NULL,certificate_subject TEXT,certificate_serial TEXT,metadata_json TEXT NOT NULL DEFAULT '{}',created_at TEXT NOT NULL,UNIQUE(tenant_id,envelope_id,signer_id,provider,sha256))""")
    op.execute("""CREATE TABLE IF NOT EXISTS signature_evidence_packages (id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,envelope_id TEXT NOT NULL REFERENCES signature_envelopes(id),sha256 TEXT NOT NULL,payload_json TEXT NOT NULL,created_at TEXT NOT NULL,UNIQUE(tenant_id,envelope_id,sha256))""")
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS pige360_tenant_{table} ON {table}")
        op.execute(f"CREATE POLICY pige360_tenant_{table} ON {table} USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true))")

def downgrade() -> None:
    for table in reversed(TABLES):
        op.execute(f"DROP TABLE IF EXISTS {table}")
