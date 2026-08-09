"""Library circulation policies, transportation operations and health care records."""
from __future__ import annotations
from alembic import op

revision="0016_student_services"
down_revision="0015_workflows"
branch_labels=None
depends_on=None

TABLES=(
 "library_policies","library_reservations","library_fines","library_loan_events",
 "transport_route_schedules","transport_trip_events","transport_occurrences",
 "health_incidents","medication_authorizations","medication_administrations",
)

def upgrade() -> None:
    op.execute("ALTER TABLE library_loans ADD COLUMN IF NOT EXISTS policy_version INTEGER")
    op.execute("""
CREATE TABLE IF NOT EXISTS library_policies (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, code TEXT NOT NULL DEFAULT 'default', version INTEGER NOT NULL,
  effective_from TEXT NOT NULL, max_loan_days INTEGER NOT NULL DEFAULT 14, max_renewals INTEGER NOT NULL DEFAULT 2,
  grace_days INTEGER NOT NULL DEFAULT 0, daily_fine NUMERIC NOT NULL DEFAULT 0, reservation_hold_hours INTEGER NOT NULL DEFAULT 48,
  state TEXT NOT NULL DEFAULT 'active', created_by TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id, code, version)
);
CREATE TABLE IF NOT EXISTS library_reservations (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, library_item_id TEXT NOT NULL REFERENCES library_items(id),
  person_id TEXT NOT NULL REFERENCES people(id), state TEXT NOT NULL DEFAULT 'queued', queued_at TEXT NOT NULL,
  ready_at TEXT, expires_at TEXT, fulfilled_at TEXT, cancelled_at TEXT, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_library_reservations_queue ON library_reservations(tenant_id, library_item_id, state, queued_at);
CREATE UNIQUE INDEX IF NOT EXISTS ux_library_reservations_active ON library_reservations(tenant_id, library_item_id, person_id) WHERE state IN ('queued','ready');
CREATE TABLE IF NOT EXISTS library_fines (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, library_loan_id TEXT NOT NULL REFERENCES library_loans(id),
  person_id TEXT NOT NULL REFERENCES people(id), amount NUMERIC NOT NULL, reason TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'open',
  issued_at TEXT NOT NULL, settled_at TEXT, settlement_reason TEXT
);
CREATE INDEX IF NOT EXISTS ix_library_fines_person ON library_fines(tenant_id, person_id, state, issued_at);
CREATE TABLE IF NOT EXISTS library_loan_events (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, library_loan_id TEXT NOT NULL REFERENCES library_loans(id),
  event_type TEXT NOT NULL, payload_json TEXT NOT NULL DEFAULT '{}', actor_user_id TEXT NOT NULL, occurred_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS transport_route_schedules (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, route_id TEXT NOT NULL REFERENCES transport_routes(id),
  weekdays_json TEXT NOT NULL DEFAULT '[]', outbound_time TEXT, return_time TEXT, valid_from TEXT NOT NULL, valid_until TEXT,
  state TEXT NOT NULL DEFAULT 'active', created_by TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS transport_trip_events (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, route_id TEXT NOT NULL REFERENCES transport_routes(id),
  rider_id TEXT NOT NULL REFERENCES transport_riders(id), student_id TEXT NOT NULL REFERENCES students(id),
  event_type TEXT NOT NULL, stop_name TEXT, occurred_at TEXT NOT NULL, device_id TEXT, location_json TEXT NOT NULL DEFAULT '{}',
  idempotency_key TEXT NOT NULL, actor_user_id TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(tenant_id, idempotency_key)
);
CREATE INDEX IF NOT EXISTS ix_transport_trip_events_student ON transport_trip_events(tenant_id, student_id, occurred_at);
CREATE TABLE IF NOT EXISTS transport_occurrences (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, route_id TEXT NOT NULL REFERENCES transport_routes(id),
  student_id TEXT REFERENCES students(id), occurrence_type TEXT NOT NULL, description TEXT NOT NULL, severity TEXT NOT NULL DEFAULT 'normal',
  state TEXT NOT NULL DEFAULT 'open', reported_by TEXT NOT NULL, reported_at TEXT NOT NULL, resolved_by TEXT, resolved_at TEXT, resolution TEXT
);
CREATE TABLE IF NOT EXISTS health_incidents (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, person_id TEXT NOT NULL REFERENCES people(id),
  incident_type TEXT NOT NULL, occurred_at TEXT NOT NULL, location TEXT, summary TEXT NOT NULL, first_aid_json TEXT NOT NULL DEFAULT '{}',
  referred_to TEXT, guardian_notified_at TEXT, state TEXT NOT NULL DEFAULT 'open', reported_by TEXT NOT NULL,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, closed_at TEXT, closed_by TEXT
);
CREATE TABLE IF NOT EXISTS medication_authorizations (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, person_id TEXT NOT NULL REFERENCES people(id),
  medication_name TEXT NOT NULL, dosage TEXT NOT NULL, instructions TEXT NOT NULL, starts_on TEXT NOT NULL, ends_on TEXT,
  prescriber TEXT, guardian_person_id TEXT REFERENCES people(id), consent_document_id TEXT,
  state TEXT NOT NULL DEFAULT 'active', created_by TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS medication_administrations (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, authorization_id TEXT NOT NULL REFERENCES medication_authorizations(id),
  person_id TEXT NOT NULL REFERENCES people(id), administered_at TEXT NOT NULL, dosage TEXT NOT NULL, notes TEXT,
  administered_by TEXT NOT NULL, idempotency_key TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(tenant_id, idempotency_key)
);
""")
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS pige360_tenant_isolation ON {table}")
        op.execute(f"CREATE POLICY pige360_tenant_isolation ON {table} USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true))")

def downgrade() -> None:
    for table in reversed(TABLES):op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    op.execute("ALTER TABLE library_loans DROP COLUMN IF EXISTS policy_version")
