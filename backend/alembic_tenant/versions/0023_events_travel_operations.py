"""Eventos/viagens com inscrições, autorizações, passageiros, checkpoints e ocorrências."""
from alembic import op

revision = "0023_events_travel_operations"
down_revision = "0022_canteen_wallet_policies"
branch_labels = None
depends_on = None

TABLES = ("event_schedule_items","event_registrations","event_authorizations","trip_passengers","trip_checkpoints","trip_incidents")

def upgrade():
    op.execute("ALTER TABLE events ADD COLUMN IF NOT EXISTS registration_fee NUMERIC NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE events ADD COLUMN IF NOT EXISTS authorization_required INTEGER NOT NULL DEFAULT 0")
    op.execute("""CREATE TABLE IF NOT EXISTS event_schedule_items (
      id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, event_id TEXT NOT NULL REFERENCES events(id), sequence INTEGER NOT NULL,
      title TEXT NOT NULL, starts_at TEXT NOT NULL, ends_at TEXT NOT NULL, location TEXT, description TEXT, created_at TEXT NOT NULL,
      UNIQUE(event_id,sequence))""")
    op.execute("""CREATE TABLE IF NOT EXISTS event_registrations (
      id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, event_id TEXT NOT NULL REFERENCES events(id), person_id TEXT REFERENCES people(id),
      student_id TEXT REFERENCES students(id), guardian_id TEXT REFERENCES guardians(id), state TEXT NOT NULL DEFAULT 'confirmed',
      fee_amount NUMERIC NOT NULL DEFAULT 0, financial_contract_id TEXT REFERENCES financial_contracts(id), checked_in_at TEXT, checked_out_at TEXT,
      idempotency_key TEXT, created_by TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
      UNIQUE(tenant_id,event_id,person_id), UNIQUE(tenant_id,event_id,student_id), UNIQUE(tenant_id,idempotency_key))""")
    op.execute("""CREATE TABLE IF NOT EXISTS event_authorizations (
      id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, event_registration_id TEXT NOT NULL REFERENCES event_registrations(id),
      guardian_id TEXT NOT NULL REFERENCES guardians(id), state TEXT NOT NULL DEFAULT 'pending', consent_text TEXT,
      evidence_json TEXT NOT NULL DEFAULT '{}', decided_at TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
      UNIQUE(tenant_id,event_registration_id,guardian_id))""")
    op.execute("""CREATE TABLE IF NOT EXISTS trip_passengers (
      id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, trip_id TEXT NOT NULL REFERENCES trips(id), student_id TEXT NOT NULL REFERENCES students(id),
      guardian_id TEXT REFERENCES guardians(id), event_registration_id TEXT REFERENCES event_registrations(id), state TEXT NOT NULL DEFAULT 'confirmed',
      emergency_snapshot_json TEXT NOT NULL DEFAULT '{}', boarded_at TEXT, disembarked_at TEXT, created_by TEXT NOT NULL,
      created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(tenant_id,trip_id,student_id))""")
    op.execute("""CREATE TABLE IF NOT EXISTS trip_checkpoints (
      id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, trip_id TEXT NOT NULL REFERENCES trips(id), sequence INTEGER NOT NULL,
      name TEXT NOT NULL, planned_at TEXT, actual_at TEXT, state TEXT NOT NULL DEFAULT 'planned', notes TEXT,
      created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(trip_id,sequence))""")
    op.execute("""CREATE TABLE IF NOT EXISTS trip_incidents (
      id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, trip_id TEXT NOT NULL REFERENCES trips(id), passenger_id TEXT REFERENCES trip_passengers(id),
      incident_type TEXT NOT NULL, severity TEXT NOT NULL DEFAULT 'low', description TEXT NOT NULL, occurred_at TEXT NOT NULL,
      resolved_at TEXT, resolution TEXT, created_by TEXT NOT NULL, created_at TEXT NOT NULL)""")
    for table in TABLES:
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'DROP POLICY IF EXISTS {table}_tenant_isolation ON "{table}"')
        op.execute(f'''CREATE POLICY {table}_tenant_isolation ON "{table}" USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true))''')

def downgrade():
    for table in reversed(TABLES):
        op.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')
    op.execute("ALTER TABLE events DROP COLUMN IF EXISTS authorization_required")
    op.execute("ALTER TABLE events DROP COLUMN IF EXISTS registration_fee")
