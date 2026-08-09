"""Compliance/LGPD: avisos, consentimentos, direitos do titular, retenção e legal hold."""
from alembic import op
revision="0027_compliance_lgpd"
down_revision="0026_education_stage_progress"
branch_labels=None
depends_on=None
TABLES=("privacy_notices","processing_activities","consent_records","data_subject_requests","data_subject_request_events","retention_policies","legal_holds")

def upgrade():
    op.execute("""CREATE TABLE IF NOT EXISTS privacy_notices(id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,code TEXT NOT NULL,title TEXT NOT NULL,version INTEGER NOT NULL,content TEXT NOT NULL,effective_from DATE NOT NULL,effective_until DATE,state TEXT NOT NULL DEFAULT 'draft',sha256 TEXT NOT NULL,created_by TEXT NOT NULL,published_by TEXT,published_at TIMESTAMPTZ,created_at TIMESTAMPTZ NOT NULL,updated_at TIMESTAMPTZ NOT NULL,UNIQUE(tenant_id,code,version))""")
    op.execute("""CREATE TABLE IF NOT EXISTS processing_activities(id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,code TEXT NOT NULL,name TEXT NOT NULL,purpose TEXT NOT NULL,legal_basis TEXT NOT NULL,privacy_notice_code TEXT,data_categories_json JSONB NOT NULL DEFAULT '[]'::jsonb,data_subjects_json JSONB NOT NULL DEFAULT '[]'::jsonb,recipients_json JSONB NOT NULL DEFAULT '[]'::jsonb,international_transfer BOOLEAN NOT NULL DEFAULT FALSE,retention_rule TEXT,security_measures_json JSONB NOT NULL DEFAULT '[]'::jsonb,owner_department TEXT,state TEXT NOT NULL DEFAULT 'active',version INTEGER NOT NULL DEFAULT 1,created_by TEXT NOT NULL,created_at TIMESTAMPTZ NOT NULL,updated_at TIMESTAMPTZ NOT NULL,UNIQUE(tenant_id,code,version))""")
    op.execute("""CREATE TABLE IF NOT EXISTS consent_records(id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,subject_person_id TEXT NOT NULL REFERENCES people(id),granted_by_person_id TEXT NOT NULL REFERENCES people(id),purpose_code TEXT NOT NULL,legal_basis TEXT NOT NULL DEFAULT 'consent',privacy_notice_id TEXT REFERENCES privacy_notices(id),channel TEXT NOT NULL,evidence_json JSONB NOT NULL DEFAULT '{}'::jsonb,state TEXT NOT NULL DEFAULT 'granted',granted_at TIMESTAMPTZ NOT NULL,revoked_at TIMESTAMPTZ,revoked_by TEXT,revocation_reason TEXT,created_by TEXT NOT NULL,created_at TIMESTAMPTZ NOT NULL,updated_at TIMESTAMPTZ NOT NULL)""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_consent_subject ON consent_records(tenant_id,subject_person_id,purpose_code,state)")
    op.execute("""CREATE TABLE IF NOT EXISTS data_subject_requests(id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,protocol TEXT NOT NULL,subject_person_id TEXT NOT NULL REFERENCES people(id),requester_person_id TEXT NOT NULL REFERENCES people(id),request_type TEXT NOT NULL,description TEXT,state TEXT NOT NULL DEFAULT 'submitted',priority TEXT NOT NULL DEFAULT 'normal',due_at TIMESTAMPTZ,decision_reason TEXT,assigned_to TEXT,export_storage_key TEXT,export_sha256 TEXT,export_bytes BIGINT,exported_at TIMESTAMPTZ,fulfilled_at TIMESTAMPTZ,created_by TEXT NOT NULL,created_at TIMESTAMPTZ NOT NULL,updated_at TIMESTAMPTZ NOT NULL,UNIQUE(tenant_id,protocol))""")
    op.execute("""CREATE TABLE IF NOT EXISTS data_subject_request_events(id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,request_id TEXT NOT NULL REFERENCES data_subject_requests(id),event_type TEXT NOT NULL,from_state TEXT,to_state TEXT,details_json JSONB NOT NULL DEFAULT '{}'::jsonb,actor_id TEXT NOT NULL,occurred_at TIMESTAMPTZ NOT NULL)""")
    op.execute("""CREATE TABLE IF NOT EXISTS retention_policies(id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,data_category TEXT NOT NULL,purpose_code TEXT,retention_days INTEGER NOT NULL,disposition TEXT NOT NULL,legal_basis TEXT NOT NULL,starts_on DATE NOT NULL,state TEXT NOT NULL DEFAULT 'active',version INTEGER NOT NULL DEFAULT 1,created_by TEXT NOT NULL,created_at TIMESTAMPTZ NOT NULL,updated_at TIMESTAMPTZ NOT NULL)""")
    op.execute("""CREATE TABLE IF NOT EXISTS legal_holds(id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,person_id TEXT REFERENCES people(id),aggregate_type TEXT,aggregate_id TEXT,reason TEXT NOT NULL,starts_at TIMESTAMPTZ NOT NULL,ends_at TIMESTAMPTZ,state TEXT NOT NULL DEFAULT 'active',created_by TEXT NOT NULL,released_by TEXT,released_at TIMESTAMPTZ,created_at TIMESTAMPTZ NOT NULL,updated_at TIMESTAMPTZ NOT NULL)""")
    for table in TABLES:
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'DROP POLICY IF EXISTS {table}_tenant_isolation ON "{table}"')
        op.execute(f"CREATE POLICY {table}_tenant_isolation ON \"{table}\" USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true))")

def downgrade():
    for table in reversed(TABLES):
        op.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')
