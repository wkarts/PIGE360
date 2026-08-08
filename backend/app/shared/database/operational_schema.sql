-- PIGE360 V8 - núcleo operacional relacional local (SQLite).
-- Todas as tabelas operacionais possuem tenant_id explícito; o adaptador PostgreSQL
-- aplica RLS e database/role exclusivos por tenant na execução de produção.

CREATE TABLE IF NOT EXISTS institutions (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, legal_name TEXT NOT NULL, trade_name TEXT NOT NULL,
  cnpj TEXT, education_system TEXT, state TEXT NOT NULL DEFAULT 'active',
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(tenant_id, cnpj)
);
CREATE TABLE IF NOT EXISTS units (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, institution_id TEXT NOT NULL REFERENCES institutions(id),
  code TEXT NOT NULL, name TEXT NOT NULL, timezone TEXT NOT NULL DEFAULT 'America/Bahia', address_json TEXT NOT NULL DEFAULT '{}',
  state TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id, code)
);
CREATE TABLE IF NOT EXISTS academic_years (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, institution_id TEXT NOT NULL REFERENCES institutions(id),
  name TEXT NOT NULL, starts_on TEXT NOT NULL, ends_on TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'draft',
  version INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id, institution_id, name)
);
CREATE TABLE IF NOT EXISTS academic_periods (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, academic_year_id TEXT NOT NULL REFERENCES academic_years(id),
  name TEXT NOT NULL, period_type TEXT NOT NULL, sequence INTEGER NOT NULL DEFAULT 1,
  starts_on TEXT NOT NULL, ends_on TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'active', version INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id, academic_year_id, period_type, sequence)
);
CREATE INDEX IF NOT EXISTS ix_academic_periods_dates ON academic_periods(tenant_id, academic_year_id, starts_on, ends_on);
CREATE TABLE IF NOT EXISTS programs (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, institution_id TEXT NOT NULL REFERENCES institutions(id),
  code TEXT NOT NULL, name TEXT NOT NULL, education_level TEXT NOT NULL, modality TEXT,
  state TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id, code)
);
CREATE TABLE IF NOT EXISTS curricula (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, program_id TEXT NOT NULL REFERENCES programs(id),
  code TEXT NOT NULL, name TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1,
  effective_from TEXT NOT NULL, effective_until TEXT, state TEXT NOT NULL DEFAULT 'active',
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(tenant_id, program_id, code, version)
);
CREATE TABLE IF NOT EXISTS curriculum_components (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, curriculum_id TEXT NOT NULL REFERENCES curricula(id),
  code TEXT NOT NULL, name TEXT NOT NULL, workload_hours NUMERIC NOT NULL DEFAULT 0,
  credits NUMERIC, syllabus TEXT, state TEXT NOT NULL DEFAULT 'active',
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(tenant_id, curriculum_id, code)
);
CREATE TABLE IF NOT EXISTS class_groups (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, unit_id TEXT NOT NULL REFERENCES units(id),
  academic_year_id TEXT NOT NULL REFERENCES academic_years(id), program_id TEXT NOT NULL REFERENCES programs(id),
  curriculum_id TEXT NOT NULL REFERENCES curricula(id), code TEXT NOT NULL, name TEXT NOT NULL,
  shift TEXT, capacity INTEGER, room TEXT, state TEXT NOT NULL DEFAULT 'active',
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(tenant_id, academic_year_id, code)
);

CREATE TABLE IF NOT EXISTS people (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, full_name TEXT NOT NULL, social_name TEXT,
  cpf TEXT, birth_date TEXT, email TEXT, phone TEXT, civil_data_json TEXT NOT NULL DEFAULT '{}',
  address_json TEXT NOT NULL DEFAULT '{}', emergency_json TEXT NOT NULL DEFAULT '{}', state TEXT NOT NULL DEFAULT 'active',
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(tenant_id, cpf)
);
CREATE INDEX IF NOT EXISTS ix_people_name ON people(tenant_id, full_name);
CREATE TABLE IF NOT EXISTS students (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, person_id TEXT NOT NULL REFERENCES people(id),
  registration_number TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'active', needs_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id, registration_number), UNIQUE(tenant_id, person_id)
);
CREATE TABLE IF NOT EXISTS guardians (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, person_id TEXT NOT NULL REFERENCES people(id),
  state TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id, person_id)
);
CREATE TABLE IF NOT EXISTS guardian_students (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, guardian_id TEXT NOT NULL REFERENCES guardians(id),
  student_id TEXT NOT NULL REFERENCES students(id), relationship TEXT NOT NULL,
  is_legal INTEGER NOT NULL DEFAULT 0, is_financial INTEGER NOT NULL DEFAULT 0, pickup_authorized INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(tenant_id, guardian_id, student_id)
);
CREATE TABLE IF NOT EXISTS employees (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, person_id TEXT NOT NULL REFERENCES people(id),
  employee_number TEXT NOT NULL, department TEXT, position TEXT, admission_date TEXT, state TEXT NOT NULL DEFAULT 'active',
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id, employee_number), UNIQUE(tenant_id, person_id)
);
CREATE TABLE IF NOT EXISTS teacher_assignments (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, employee_id TEXT NOT NULL REFERENCES employees(id),
  class_group_id TEXT NOT NULL REFERENCES class_groups(id), component_id TEXT NOT NULL REFERENCES curriculum_components(id),
  starts_on TEXT NOT NULL, ends_on TEXT, role TEXT NOT NULL DEFAULT 'teacher', state TEXT NOT NULL DEFAULT 'active',
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id, employee_id, class_group_id, component_id, starts_on)
);
CREATE TABLE IF NOT EXISTS admission_candidates (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, person_id TEXT NOT NULL REFERENCES people(id),
  program_id TEXT NOT NULL REFERENCES programs(id), academic_year_id TEXT NOT NULL REFERENCES academic_years(id),
  source TEXT, score NUMERIC, rank_position INTEGER, state TEXT NOT NULL DEFAULT 'registered',
  notes TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS enrollments (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, student_id TEXT NOT NULL REFERENCES students(id),
  institution_id TEXT NOT NULL REFERENCES institutions(id), unit_id TEXT NOT NULL REFERENCES units(id),
  program_id TEXT NOT NULL REFERENCES programs(id), curriculum_id TEXT NOT NULL REFERENCES curricula(id),
  academic_year_id TEXT NOT NULL REFERENCES academic_years(id), class_group_id TEXT REFERENCES class_groups(id),
  enrollment_number TEXT NOT NULL, financial_responsible_guardian_id TEXT REFERENCES guardians(id),
  state TEXT NOT NULL DEFAULT 'pre_enrolled', enrolled_on TEXT, ended_on TEXT, version INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(tenant_id, enrollment_number)
);
CREATE INDEX IF NOT EXISTS ix_enrollments_student ON enrollments(tenant_id, student_id, state);

CREATE TABLE IF NOT EXISTS financial_contracts (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, enrollment_id TEXT REFERENCES enrollments(id),
  responsible_guardian_id TEXT REFERENCES guardians(id), description TEXT NOT NULL, total_amount NUMERIC NOT NULL,
  currency TEXT NOT NULL DEFAULT 'BRL', competence_rule TEXT NOT NULL DEFAULT 'billing', state TEXT NOT NULL DEFAULT 'draft',
  version INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS installments (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, financial_contract_id TEXT NOT NULL REFERENCES financial_contracts(id),
  sequence INTEGER NOT NULL, competence TEXT, due_date TEXT NOT NULL, original_amount NUMERIC NOT NULL,
  discount_amount NUMERIC NOT NULL DEFAULT 0, penalty_amount NUMERIC NOT NULL DEFAULT 0, interest_amount NUMERIC NOT NULL DEFAULT 0,
  paid_amount NUMERIC NOT NULL DEFAULT 0, state TEXT NOT NULL DEFAULT 'open', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(financial_contract_id, sequence)
);
CREATE INDEX IF NOT EXISTS ix_installments_due ON installments(tenant_id, state, due_date);
CREATE TABLE IF NOT EXISTS payments (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, method TEXT NOT NULL, amount NUMERIC NOT NULL, paid_at TEXT NOT NULL,
  external_reference TEXT, state TEXT NOT NULL DEFAULT 'confirmed', idempotency_key TEXT,
  metadata_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL,
  UNIQUE(tenant_id, idempotency_key)
);
CREATE TABLE IF NOT EXISTS payment_allocations (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, payment_id TEXT NOT NULL REFERENCES payments(id),
  installment_id TEXT NOT NULL REFERENCES installments(id), amount NUMERIC NOT NULL, created_at TEXT NOT NULL,
  UNIQUE(payment_id, installment_id)
);
CREATE TABLE IF NOT EXISTS ledger_entries (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, entry_type TEXT NOT NULL, reference_type TEXT NOT NULL, reference_id TEXT NOT NULL,
  debit_account TEXT, credit_account TEXT, amount NUMERIC NOT NULL, competence TEXT, occurred_at TEXT NOT NULL,
  reversal_of_id TEXT REFERENCES ledger_entries(id), description TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS bank_accounts (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, name TEXT NOT NULL, bank_code TEXT, branch TEXT, account_number TEXT,
  pix_key TEXT, pix_receiver_name TEXT, pix_receiver_city TEXT, state TEXT NOT NULL DEFAULT 'active',
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS pix_charges (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, bank_account_id TEXT NOT NULL REFERENCES bank_accounts(id),
  installment_id TEXT NOT NULL REFERENCES installments(id), txid TEXT NOT NULL, amount NUMERIC NOT NULL,
  br_code TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'pending', expires_at TEXT, paid_at TEXT,
  end_to_end_id TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(tenant_id, txid)
);
CREATE TABLE IF NOT EXISTS bank_imports (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, bank_account_id TEXT NOT NULL REFERENCES bank_accounts(id),
  source_type TEXT NOT NULL, source_sha256 TEXT NOT NULL, imported_at TEXT NOT NULL, created_by TEXT,
  UNIQUE(tenant_id, source_sha256)
);
CREATE TABLE IF NOT EXISTS bank_transactions (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, bank_import_id TEXT REFERENCES bank_imports(id),
  bank_account_id TEXT NOT NULL REFERENCES bank_accounts(id), external_id TEXT, posted_at TEXT NOT NULL,
  description TEXT, amount NUMERIC NOT NULL, direction TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'unmatched',
  payment_id TEXT REFERENCES payments(id), matched_at TEXT, matched_by TEXT, reconciliation_reason TEXT, created_at TEXT NOT NULL,
  UNIQUE(tenant_id, bank_account_id, external_id)
);

CREATE TABLE IF NOT EXISTS services (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, code TEXT NOT NULL, name TEXT NOT NULL, description TEXT,
  price NUMERIC NOT NULL DEFAULT 0, recurrence TEXT, nbs TEXT, lc116_code TEXT, municipal_code TEXT, cnae TEXT,
  fiscal_profile_json TEXT NOT NULL DEFAULT '{}', state TEXT NOT NULL DEFAULT 'active',
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(tenant_id, code)
);
CREATE TABLE IF NOT EXISTS service_orders (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, enrollment_id TEXT REFERENCES enrollments(id),
  responsible_guardian_id TEXT REFERENCES guardians(id), competence TEXT, state TEXT NOT NULL DEFAULT 'draft',
  total_amount NUMERIC NOT NULL DEFAULT 0, financial_contract_id TEXT REFERENCES financial_contracts(id),
  fiscal_document_id TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS service_order_items (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, service_order_id TEXT NOT NULL REFERENCES service_orders(id),
  service_id TEXT NOT NULL REFERENCES services(id), quantity NUMERIC NOT NULL, unit_price NUMERIC NOT NULL,
  total_amount NUMERIC NOT NULL, created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS products (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, sku TEXT NOT NULL, barcode TEXT, name TEXT NOT NULL,
  product_type TEXT NOT NULL DEFAULT 'product', ncm TEXT, cest TEXT, unit TEXT NOT NULL DEFAULT 'UN',
  cost NUMERIC NOT NULL DEFAULT 0, sale_price NUMERIC NOT NULL DEFAULT 0, fiscal_profile_json TEXT NOT NULL DEFAULT '{}',
  allergen_json TEXT NOT NULL DEFAULT '[]', restriction_json TEXT NOT NULL DEFAULT '{}', state TEXT NOT NULL DEFAULT 'active',
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(tenant_id, sku), UNIQUE(tenant_id, barcode)
);
CREATE TABLE IF NOT EXISTS stock_balances (
  tenant_id TEXT NOT NULL, product_id TEXT NOT NULL REFERENCES products(id), warehouse TEXT NOT NULL DEFAULT 'default',
  quantity NUMERIC NOT NULL DEFAULT 0, reserved NUMERIC NOT NULL DEFAULT 0, updated_at TEXT NOT NULL,
  PRIMARY KEY(tenant_id, product_id, warehouse)
);
CREATE TABLE IF NOT EXISTS stock_movements (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, product_id TEXT NOT NULL REFERENCES products(id), warehouse TEXT NOT NULL DEFAULT 'default',
  movement_type TEXT NOT NULL, quantity NUMERIC NOT NULL, unit_cost NUMERIC, reference_type TEXT, reference_id TEXT,
  reason TEXT, occurred_at TEXT NOT NULL, created_by TEXT
);
CREATE TABLE IF NOT EXISTS cash_sessions (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, terminal_code TEXT NOT NULL, operator_user_id TEXT NOT NULL,
  opened_at TEXT NOT NULL, opening_amount NUMERIC NOT NULL DEFAULT 0, closed_at TEXT, closing_amount NUMERIC,
  state TEXT NOT NULL DEFAULT 'open', created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sales (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, cash_session_id TEXT REFERENCES cash_sessions(id),
  customer_person_id TEXT REFERENCES people(id), student_id TEXT REFERENCES students(id), canteen_location_id TEXT REFERENCES canteen_locations(id), channel TEXT NOT NULL,
  subtotal NUMERIC NOT NULL, discount NUMERIC NOT NULL DEFAULT 0, total_amount NUMERIC NOT NULL,
  state TEXT NOT NULL DEFAULT 'completed', fiscal_status TEXT NOT NULL DEFAULT 'pending', idempotency_key TEXT,
  created_by TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(tenant_id, idempotency_key)
);
CREATE TABLE IF NOT EXISTS sale_items (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, sale_id TEXT NOT NULL REFERENCES sales(id),
  product_id TEXT NOT NULL REFERENCES products(id), quantity NUMERIC NOT NULL, unit_price NUMERIC NOT NULL,
  discount NUMERIC NOT NULL DEFAULT 0, total_amount NUMERIC NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sale_payments (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, sale_id TEXT NOT NULL REFERENCES sales(id),
  method TEXT NOT NULL, amount NUMERIC NOT NULL, external_reference TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS suppliers (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, legal_name TEXT NOT NULL, trade_name TEXT, cnpj TEXT,
  email TEXT, phone TEXT, state TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id, cnpj)
);
CREATE TABLE IF NOT EXISTS purchase_orders (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, supplier_id TEXT NOT NULL REFERENCES suppliers(id),
  order_number TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'draft', total_amount NUMERIC NOT NULL DEFAULT 0,
  expected_on TEXT, received_at TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id, order_number)
);
CREATE TABLE IF NOT EXISTS purchase_order_items (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, purchase_order_id TEXT NOT NULL REFERENCES purchase_orders(id),
  product_id TEXT NOT NULL REFERENCES products(id), quantity NUMERIC NOT NULL, unit_cost NUMERIC NOT NULL,
  received_quantity NUMERIC NOT NULL DEFAULT 0, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS assets (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, asset_number TEXT NOT NULL, description TEXT NOT NULL,
  acquisition_date TEXT, acquisition_cost NUMERIC, location TEXT, responsible_person_id TEXT REFERENCES people(id),
  state TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id, asset_number)
);

CREATE TABLE IF NOT EXISTS fiscal_profiles (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, establishment_name TEXT NOT NULL, cnpj TEXT NOT NULL,
  tax_regime TEXT NOT NULL, uf TEXT NOT NULL, municipality_code TEXT, environment TEXT NOT NULL DEFAULT 'homologation',
  provider_connection_id TEXT REFERENCES integration_connections(id),
  state TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id, cnpj)
);
CREATE TABLE IF NOT EXISTS fiscal_rules (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, fiscal_profile_id TEXT NOT NULL REFERENCES fiscal_profiles(id),
  operation_type TEXT NOT NULL, item_kind TEXT NOT NULL, classification_key TEXT,
  effective_from TEXT NOT NULL, effective_until TEXT, rules_json TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'active', version INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS fiscal_documents (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, fiscal_profile_id TEXT REFERENCES fiscal_profiles(id),
  document_type TEXT NOT NULL, source_type TEXT NOT NULL, source_id TEXT NOT NULL, environment TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'requested', access_key TEXT, protocol TEXT, number TEXT, series TEXT,
  provider_connection_id TEXT REFERENCES integration_connections(id), provider_document_id TEXT, provider_status TEXT NOT NULL DEFAULT 'not_configured',
  attempts INTEGER NOT NULL DEFAULT 0, last_attempt_at TEXT,
  totals_json TEXT NOT NULL DEFAULT '{}', request_json TEXT NOT NULL DEFAULT '{}', response_json TEXT NOT NULL DEFAULT '{}',
  xml_storage_key TEXT, pdf_storage_key TEXT, xml_sha256 TEXT, error_code TEXT, error_message TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(tenant_id, document_type, source_type, source_id)
);
CREATE TABLE IF NOT EXISTS fiscal_document_events (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, fiscal_document_id TEXT NOT NULL REFERENCES fiscal_documents(id),
  event_type TEXT NOT NULL, state TEXT NOT NULL, provider_connection_id TEXT REFERENCES integration_connections(id),
  provider_event_id TEXT, payload_json TEXT NOT NULL DEFAULT '{}', xml_storage_key TEXT, xml_sha256 TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fiscal_document_events_document ON fiscal_document_events(tenant_id,fiscal_document_id,created_at);

CREATE TABLE IF NOT EXISTS employment_contracts (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, employee_id TEXT NOT NULL REFERENCES employees(id),
  contract_type TEXT NOT NULL, starts_on TEXT NOT NULL, ends_on TEXT, salary NUMERIC, weekly_hours NUMERIC,
  schedule_json TEXT NOT NULL DEFAULT '{}', state TEXT NOT NULL DEFAULT 'active', version INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS payroll_runs (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, competence TEXT NOT NULL, run_type TEXT NOT NULL DEFAULT 'monthly',
  state TEXT NOT NULL DEFAULT 'draft', gross_total NUMERIC NOT NULL DEFAULT 0, deductions_total NUMERIC NOT NULL DEFAULT 0,
  net_total NUMERIC NOT NULL DEFAULT 0, version INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id, competence, run_type)
);
CREATE TABLE IF NOT EXISTS payroll_entries (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, payroll_run_id TEXT NOT NULL REFERENCES payroll_runs(id),
  employee_id TEXT NOT NULL REFERENCES employees(id), gross_amount NUMERIC NOT NULL DEFAULT 0,
  deductions_amount NUMERIC NOT NULL DEFAULT 0, net_amount NUMERIC NOT NULL DEFAULT 0,
  items_json TEXT NOT NULL DEFAULT '[]', state TEXT NOT NULL DEFAULT 'calculated', created_at TEXT NOT NULL,
  UNIQUE(payroll_run_id, employee_id)
);
CREATE TABLE IF NOT EXISTS time_entries (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, employee_id TEXT NOT NULL REFERENCES employees(id),
  occurred_at TEXT NOT NULL, event_type TEXT NOT NULL, origin TEXT NOT NULL, device_id TEXT,
  latitude NUMERIC, longitude NUMERIC, idempotency_key TEXT, state TEXT NOT NULL DEFAULT 'valid',
  created_at TEXT NOT NULL, UNIQUE(tenant_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS events (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, event_type TEXT NOT NULL, name TEXT NOT NULL,
  starts_at TEXT NOT NULL, ends_at TEXT NOT NULL, location TEXT, capacity INTEGER, state TEXT NOT NULL DEFAULT 'draft',
  budget NUMERIC, registration_fee NUMERIC NOT NULL DEFAULT 0, authorization_required INTEGER NOT NULL DEFAULT 0,
  payload_json TEXT NOT NULL DEFAULT '{}', version INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS event_schedule_items (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, event_id TEXT NOT NULL REFERENCES events(id), sequence INTEGER NOT NULL,
  title TEXT NOT NULL, starts_at TEXT NOT NULL, ends_at TEXT NOT NULL, location TEXT, description TEXT,
  created_at TEXT NOT NULL, UNIQUE(event_id, sequence)
);
CREATE TABLE IF NOT EXISTS event_registrations (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, event_id TEXT NOT NULL REFERENCES events(id), person_id TEXT REFERENCES people(id),
  student_id TEXT REFERENCES students(id), guardian_id TEXT REFERENCES guardians(id), state TEXT NOT NULL DEFAULT 'confirmed',
  fee_amount NUMERIC NOT NULL DEFAULT 0, financial_contract_id TEXT REFERENCES financial_contracts(id),
  checked_in_at TEXT, checked_out_at TEXT, idempotency_key TEXT, created_by TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id,event_id,person_id), UNIQUE(tenant_id,event_id,student_id), UNIQUE(tenant_id,idempotency_key)
);
CREATE TABLE IF NOT EXISTS event_authorizations (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, event_registration_id TEXT NOT NULL REFERENCES event_registrations(id),
  guardian_id TEXT NOT NULL REFERENCES guardians(id), state TEXT NOT NULL DEFAULT 'pending', consent_text TEXT,
  evidence_json TEXT NOT NULL DEFAULT '{}', decided_at TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id,event_registration_id,guardian_id)
);
CREATE TABLE IF NOT EXISTS trips (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, event_id TEXT REFERENCES events(id), name TEXT NOT NULL,
  destination TEXT NOT NULL, starts_at TEXT NOT NULL, ends_at TEXT NOT NULL,
  itinerary_json TEXT NOT NULL DEFAULT '[]', vehicles_json TEXT NOT NULL DEFAULT '[]', emergency_json TEXT NOT NULL DEFAULT '{}',
  state TEXT NOT NULL DEFAULT 'draft', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS trip_passengers (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, trip_id TEXT NOT NULL REFERENCES trips(id), student_id TEXT NOT NULL REFERENCES students(id),
  guardian_id TEXT REFERENCES guardians(id), event_registration_id TEXT REFERENCES event_registrations(id), state TEXT NOT NULL DEFAULT 'confirmed',
  emergency_snapshot_json TEXT NOT NULL DEFAULT '{}', boarded_at TEXT, disembarked_at TEXT, created_by TEXT NOT NULL,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(tenant_id,trip_id,student_id)
);
CREATE TABLE IF NOT EXISTS trip_checkpoints (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, trip_id TEXT NOT NULL REFERENCES trips(id), sequence INTEGER NOT NULL,
  name TEXT NOT NULL, planned_at TEXT, actual_at TEXT, state TEXT NOT NULL DEFAULT 'planned', notes TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(trip_id,sequence)
);
CREATE TABLE IF NOT EXISTS trip_incidents (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, trip_id TEXT NOT NULL REFERENCES trips(id), passenger_id TEXT REFERENCES trip_passengers(id),
  incident_type TEXT NOT NULL, severity TEXT NOT NULL DEFAULT 'low', description TEXT NOT NULL, occurred_at TEXT NOT NULL,
  resolved_at TEXT, resolution TEXT, created_by TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS notices (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL, priority TEXT NOT NULL DEFAULT 'normal',
  audience_json TEXT NOT NULL, channels_json TEXT NOT NULL DEFAULT '["internal"]', scheduled_at TEXT, expires_at TEXT,
  state TEXT NOT NULL DEFAULT 'draft', version INTEGER NOT NULL DEFAULT 1, created_by TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS notice_versions (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, notice_id TEXT NOT NULL REFERENCES notices(id), version INTEGER NOT NULL,
  snapshot_json TEXT NOT NULL, change_reason TEXT, created_by TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(notice_id, version)
);
CREATE TABLE IF NOT EXISTS notice_receipts (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, notice_id TEXT NOT NULL REFERENCES notices(id), person_id TEXT NOT NULL REFERENCES people(id),
  first_seen_at TEXT, acknowledged_at TEXT, created_at TEXT NOT NULL, UNIQUE(tenant_id, notice_id, person_id)
);
CREATE TABLE IF NOT EXISTS service_requests (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, protocol TEXT NOT NULL, requester_person_id TEXT REFERENCES people(id),
  request_type TEXT NOT NULL, subject TEXT NOT NULL, description TEXT, priority TEXT NOT NULL DEFAULT 'normal',
  department TEXT, assigned_user_id TEXT, sla_due_at TEXT, state TEXT NOT NULL DEFAULT 'open', version INTEGER NOT NULL DEFAULT 1,
  request_type_version INTEGER, form_data_json TEXT NOT NULL DEFAULT '{}', workflow_instance_id TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(tenant_id, protocol)
);
CREATE TABLE IF NOT EXISTS request_type_definitions (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, code TEXT NOT NULL, name TEXT NOT NULL, department TEXT, default_sla_hours INTEGER NOT NULL DEFAULT 72,
  state TEXT NOT NULL DEFAULT 'draft', current_version INTEGER NOT NULL DEFAULT 1, created_by TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id, code)
);
CREATE TABLE IF NOT EXISTS request_type_versions (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, request_type_id TEXT NOT NULL REFERENCES request_type_definitions(id), version INTEGER NOT NULL,
  form_schema_json TEXT NOT NULL DEFAULT '{}', workflow_json TEXT NOT NULL DEFAULT '{}', change_reason TEXT, state TEXT NOT NULL DEFAULT 'draft',
  created_by TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(request_type_id, version)
);
CREATE TABLE IF NOT EXISTS service_request_events (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, service_request_id TEXT NOT NULL REFERENCES service_requests(id), event_type TEXT NOT NULL,
  from_state TEXT, to_state TEXT, reason TEXT, actor_user_id TEXT NOT NULL, occurred_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS service_request_comments (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, service_request_id TEXT NOT NULL REFERENCES service_requests(id), author_user_id TEXT NOT NULL,
  body TEXT NOT NULL, visibility TEXT NOT NULL DEFAULT 'requester', created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS workflow_definitions (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, code TEXT NOT NULL, name TEXT NOT NULL,
  aggregate_type TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'draft', current_version INTEGER NOT NULL DEFAULT 1,
  created_by TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(tenant_id, code)
);
CREATE TABLE IF NOT EXISTS workflow_definition_versions (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, workflow_definition_id TEXT NOT NULL REFERENCES workflow_definitions(id),
  version INTEGER NOT NULL, steps_json TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'draft', change_reason TEXT,
  created_by TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(workflow_definition_id, version)
);
CREATE TABLE IF NOT EXISTS workflow_instances (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, workflow_definition_id TEXT NOT NULL REFERENCES workflow_definitions(id),
  definition_version INTEGER NOT NULL, aggregate_type TEXT NOT NULL, aggregate_id TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'active', current_step_key TEXT, context_json TEXT NOT NULL DEFAULT '{}',
  started_by TEXT NOT NULL, started_at TEXT NOT NULL, completed_at TEXT, cancelled_at TEXT,
  version INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS ix_workflow_instances_aggregate ON workflow_instances(tenant_id, aggregate_type, aggregate_id, started_at);
CREATE TABLE IF NOT EXISTS workflow_tasks (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, workflow_instance_id TEXT NOT NULL REFERENCES workflow_instances(id),
  step_key TEXT NOT NULL, step_name TEXT NOT NULL, task_type TEXT NOT NULL, assignee_roles_json TEXT NOT NULL DEFAULT '[]',
  assignee_user_id TEXT, state TEXT NOT NULL DEFAULT 'open', due_at TEXT, decision TEXT, comment TEXT,
  completed_by TEXT, completed_at TEXT, sla_breached_at TEXT, escalation_count INTEGER NOT NULL DEFAULT 0,
  version INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_workflow_tasks_state ON workflow_tasks(tenant_id, state, due_at, created_at);
CREATE TABLE IF NOT EXISTS workflow_events (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, workflow_instance_id TEXT NOT NULL REFERENCES workflow_instances(id),
  event_type TEXT NOT NULL, from_state TEXT, to_state TEXT, from_step_key TEXT, to_step_key TEXT,
  actor_user_id TEXT, decision TEXT, comment TEXT, payload_json TEXT NOT NULL DEFAULT '{}', occurred_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_workflow_events_instance ON workflow_events(tenant_id, workflow_instance_id, occurred_at);
CREATE TABLE IF NOT EXISTS automation_rules (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, name TEXT NOT NULL, trigger_type TEXT NOT NULL,
  trigger_key TEXT NOT NULL, conditions_json TEXT NOT NULL DEFAULT '{}', actions_json TEXT NOT NULL DEFAULT '[]',
  state TEXT NOT NULL DEFAULT 'active', version INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS automation_executions (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, rule_id TEXT NOT NULL REFERENCES automation_rules(id),
  event_id TEXT, state TEXT NOT NULL, dry_run INTEGER NOT NULL DEFAULT 0, input_json TEXT NOT NULL,
  result_json TEXT NOT NULL DEFAULT '{}', error TEXT, started_at TEXT NOT NULL, finished_at TEXT
);
CREATE TABLE IF NOT EXISTS notifications (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, recipient_person_id TEXT REFERENCES people(id),
  channel TEXT NOT NULL, template_key TEXT, subject TEXT, body TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'queued',
  provider_message_id TEXT, scheduled_at TEXT, sent_at TEXT, attempts INTEGER NOT NULL DEFAULT 0,
  idempotency_key TEXT, created_at TEXT NOT NULL, UNIQUE(tenant_id, idempotency_key)
);
CREATE TABLE IF NOT EXISTS communication_templates (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, template_key TEXT NOT NULL, name TEXT NOT NULL,
  channel TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'draft', current_version INTEGER NOT NULL DEFAULT 1,
  created_by TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(tenant_id, template_key)
);
CREATE TABLE IF NOT EXISTS communication_template_versions (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, template_id TEXT NOT NULL REFERENCES communication_templates(id),
  version INTEGER NOT NULL, subject_template TEXT, body_template TEXT NOT NULL, variables_json TEXT NOT NULL DEFAULT '[]',
  state TEXT NOT NULL DEFAULT 'draft', change_reason TEXT, created_by TEXT NOT NULL, created_at TEXT NOT NULL,
  UNIQUE(template_id, version)
);
CREATE TABLE IF NOT EXISTS communication_preferences (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, person_id TEXT NOT NULL REFERENCES people(id), channel TEXT NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 1, quiet_hours_json TEXT NOT NULL DEFAULT '{}', updated_by TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id, person_id, channel)
);
CREATE TABLE IF NOT EXISTS notification_events (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, notification_id TEXT NOT NULL REFERENCES notifications(id),
  event_type TEXT NOT NULL, state TEXT NOT NULL, provider_message_id TEXT, details_json TEXT NOT NULL DEFAULT '{}',
  occurred_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_notification_events_notification ON notification_events(tenant_id, notification_id, occurred_at);

CREATE TABLE IF NOT EXISTS library_items (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, inventory_code TEXT NOT NULL, title TEXT NOT NULL,
  authors TEXT, isbn TEXT, category TEXT, item_type TEXT NOT NULL DEFAULT 'book', state TEXT NOT NULL DEFAULT 'available',
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(tenant_id, inventory_code)
);
CREATE TABLE IF NOT EXISTS library_loans (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, library_item_id TEXT NOT NULL REFERENCES library_items(id),
  person_id TEXT NOT NULL REFERENCES people(id), loaned_at TEXT NOT NULL, due_at TEXT NOT NULL,
  returned_at TEXT, renewal_count INTEGER NOT NULL DEFAULT 0, fine_amount NUMERIC NOT NULL DEFAULT 0, policy_version INTEGER,
  state TEXT NOT NULL DEFAULT 'open', created_at TEXT NOT NULL
);
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
CREATE TABLE IF NOT EXISTS transport_routes (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, code TEXT NOT NULL, name TEXT NOT NULL,
  vehicle TEXT, driver_person_id TEXT REFERENCES people(id), monitor_person_id TEXT REFERENCES people(id),
  stops_json TEXT NOT NULL DEFAULT '[]', state TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id, code)
);
CREATE TABLE IF NOT EXISTS transport_riders (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, route_id TEXT NOT NULL REFERENCES transport_routes(id),
  student_id TEXT NOT NULL REFERENCES students(id), boarding_stop TEXT, dropoff_stop TEXT,
  state TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL, UNIQUE(tenant_id, route_id, student_id)
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
CREATE TABLE IF NOT EXISTS health_records (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, person_id TEXT NOT NULL REFERENCES people(id),
  record_type TEXT NOT NULL, summary TEXT NOT NULL, details_json TEXT NOT NULL DEFAULT '{}',
  sensitivity TEXT NOT NULL DEFAULT 'restricted', valid_from TEXT, valid_until TEXT, state TEXT NOT NULL DEFAULT 'active',
  created_by TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS health_access_log (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, health_record_id TEXT NOT NULL REFERENCES health_records(id),
  actor_user_id TEXT NOT NULL, reason TEXT NOT NULL, accessed_at TEXT NOT NULL
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
  prescriber TEXT, guardian_person_id TEXT REFERENCES people(id), consent_document_id TEXT REFERENCES documents(id),
  state TEXT NOT NULL DEFAULT 'active', created_by TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS medication_administrations (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, authorization_id TEXT NOT NULL REFERENCES medication_authorizations(id),
  person_id TEXT NOT NULL REFERENCES people(id), administered_at TEXT NOT NULL, dosage TEXT NOT NULL, notes TEXT,
  administered_by TEXT NOT NULL, idempotency_key TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(tenant_id, idempotency_key)
);
CREATE TABLE IF NOT EXISTS documents (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, owner_type TEXT NOT NULL, owner_id TEXT,
  category TEXT NOT NULL, original_filename TEXT NOT NULL, mime_type TEXT NOT NULL, bytes INTEGER NOT NULL,
  sha256 TEXT NOT NULL, storage_key TEXT NOT NULL, antivirus_state TEXT NOT NULL DEFAULT 'not_configured',
  state TEXT NOT NULL DEFAULT 'active', created_by TEXT NOT NULL, created_at TEXT NOT NULL,
  UNIQUE(tenant_id, sha256, category, owner_type, owner_id)
);
CREATE TABLE IF NOT EXISTS integration_connections (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, provider TEXT NOT NULL, name TEXT NOT NULL,
  environment TEXT NOT NULL DEFAULT 'production', capabilities_json TEXT NOT NULL DEFAULT '[]',
  secret_reference TEXT, config_json TEXT NOT NULL DEFAULT '{}', state TEXT NOT NULL DEFAULT 'not_configured',
  last_health_at TEXT, last_health_state TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS integration_runs (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, connection_id TEXT NOT NULL REFERENCES integration_connections(id),
  direction TEXT NOT NULL, capability TEXT NOT NULL, state TEXT NOT NULL, cursor TEXT,
  stats_json TEXT NOT NULL DEFAULT '{}', error TEXT, started_at TEXT NOT NULL, finished_at TEXT
);
CREATE TABLE IF NOT EXISTS integration_operation_keys (
  tenant_id TEXT NOT NULL, connection_id TEXT NOT NULL REFERENCES integration_connections(id),
  idempotency_key TEXT NOT NULL, capability TEXT NOT NULL, request_hash TEXT NOT NULL,
  state TEXT NOT NULL, response_json TEXT, error TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  PRIMARY KEY(tenant_id, connection_id, idempotency_key)
);
CREATE TABLE IF NOT EXISTS government_export_layouts (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, authority TEXT NOT NULL, layout_code TEXT NOT NULL,
  version TEXT NOT NULL, effective_from TEXT NOT NULL, effective_until TEXT,
  schema_json TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL,
  UNIQUE(tenant_id, authority, layout_code, version)
);
CREATE TABLE IF NOT EXISTS government_exports (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, layout_id TEXT NOT NULL REFERENCES government_export_layouts(id),
  reference_period TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'generated', record_count INTEGER NOT NULL DEFAULT 0,
  sha256 TEXT NOT NULL, storage_key TEXT NOT NULL, validation_json TEXT NOT NULL DEFAULT '{}',
  protocol TEXT, created_by TEXT NOT NULL, created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS contract_templates (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, contract_type TEXT NOT NULL, name TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'draft', current_version INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS contract_template_versions (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, template_id TEXT NOT NULL REFERENCES contract_templates(id),
  version INTEGER NOT NULL, body_text TEXT NOT NULL, variables_json TEXT NOT NULL DEFAULT '[]',
  rules_json TEXT NOT NULL DEFAULT '{}', sha256 TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'draft',
  created_by TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(template_id, version)
);
CREATE TABLE IF NOT EXISTS legal_contracts (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, contract_type TEXT NOT NULL, number TEXT NOT NULL,
  enrollment_id TEXT REFERENCES enrollments(id), financial_contract_id TEXT REFERENCES financial_contracts(id),
  template_version_id TEXT REFERENCES contract_template_versions(id), state TEXT NOT NULL DEFAULT 'draft',
  effective_from TEXT, effective_until TEXT, validation_code TEXT, document_sha256 TEXT, document_storage_key TEXT,
  signed_document_sha256 TEXT, signed_document_storage_key TEXT, signature_profile TEXT,
  snapshot_id TEXT, version INTEGER NOT NULL DEFAULT 1, created_by TEXT NOT NULL, updated_by TEXT NOT NULL,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(tenant_id, number)
);
CREATE TABLE IF NOT EXISTS contract_parties (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, contract_id TEXT NOT NULL REFERENCES legal_contracts(id),
  party_type TEXT NOT NULL, person_id TEXT REFERENCES people(id), legal_name TEXT,
  document_number TEXT, role TEXT NOT NULL, signing_required INTEGER NOT NULL DEFAULT 1,
  signing_order INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS contract_events (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, contract_id TEXT NOT NULL REFERENCES legal_contracts(id),
  event_type TEXT NOT NULL, payload_json TEXT NOT NULL DEFAULT '{}', actor_id TEXT, reason TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS contract_versions (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, contract_id TEXT NOT NULL REFERENCES legal_contracts(id),
  version INTEGER NOT NULL, state TEXT NOT NULL, effective_from TEXT, effective_until TEXT,
  document_sha256 TEXT, document_storage_key TEXT, signed_document_sha256 TEXT, signed_document_storage_key TEXT, signature_profile TEXT,
  snapshot_id TEXT, reason TEXT, actor_id TEXT, created_at TEXT NOT NULL,
  UNIQUE(tenant_id, contract_id, version)
);
CREATE TABLE IF NOT EXISTS contract_amendments (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, contract_id TEXT NOT NULL REFERENCES legal_contracts(id),
  amendment_contract_id TEXT NOT NULL REFERENCES legal_contracts(id),
  amendment_type TEXT NOT NULL, title TEXT NOT NULL, payload_json TEXT NOT NULL DEFAULT '{}',
  effective_from TEXT, state TEXT NOT NULL DEFAULT 'draft', version INTEGER NOT NULL DEFAULT 1,
  created_by TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS contract_relationships (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, source_contract_id TEXT NOT NULL REFERENCES legal_contracts(id),
  target_contract_id TEXT NOT NULL REFERENCES legal_contracts(id), relationship_type TEXT NOT NULL,
  created_by TEXT NOT NULL, created_at TEXT NOT NULL,
  UNIQUE(tenant_id, source_contract_id, target_contract_id, relationship_type)
);

CREATE TABLE IF NOT EXISTS payroll_rules (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, code TEXT NOT NULL, name TEXT NOT NULL,
  direction TEXT NOT NULL, calculation_type TEXT NOT NULL, basis TEXT NOT NULL,
  value NUMERIC NOT NULL, effective_from TEXT NOT NULL, effective_until TEXT,
  priority INTEGER NOT NULL DEFAULT 100, state TEXT NOT NULL DEFAULT 'active', version INTEGER NOT NULL DEFAULT 1,
  metadata_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id, code, version)
);
CREATE TABLE IF NOT EXISTS hr_events (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, employee_id TEXT NOT NULL REFERENCES employees(id),
  event_type TEXT NOT NULL, starts_on TEXT NOT NULL, ends_on TEXT, payload_json TEXT NOT NULL DEFAULT '{}',
  state TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);

-- IBPT WWSoftwares: snapshots versionados; nunca consultar provider por venda.
CREATE TABLE IF NOT EXISTS ibpt_sync_runs (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, uf TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'queued', snapshot_id TEXT, requested_by TEXT,
  requested_at TEXT NOT NULL, started_at TEXT, finished_at TEXT,
  error_code TEXT, error_message TEXT
);
CREATE INDEX IF NOT EXISTS ix_ibpt_sync_runs_state ON ibpt_sync_runs(tenant_id, state, requested_at);
CREATE TABLE IF NOT EXISTS ibpt_snapshots (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, uf TEXT NOT NULL,
  source_url TEXT NOT NULL, sha256 TEXT NOT NULL, storage_key TEXT NOT NULL,
  rows_count INTEGER NOT NULL, source_version TEXT, effective_from TEXT, effective_to TEXT,
  state TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL,
  UNIQUE(tenant_id, uf, sha256)
);
CREATE INDEX IF NOT EXISTS ix_ibpt_snapshots_active ON ibpt_snapshots(tenant_id, uf, state, created_at);
CREATE TABLE IF NOT EXISTS ibpt_rates (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, snapshot_id TEXT NOT NULL REFERENCES ibpt_snapshots(id),
  uf TEXT NOT NULL, code TEXT NOT NULL, ex TEXT NOT NULL DEFAULT '', item_type TEXT NOT NULL DEFAULT '',
  description TEXT NOT NULL, national_federal NUMERIC NOT NULL DEFAULT 0,
  imported_federal NUMERIC NOT NULL DEFAULT 0, state_rate NUMERIC NOT NULL DEFAULT 0,
  municipal_rate NUMERIC NOT NULL DEFAULT 0, effective_from TEXT, effective_to TEXT,
  source_version TEXT, source_name TEXT, created_at TEXT NOT NULL,
  UNIQUE(tenant_id, snapshot_id, code, ex, item_type)
);
CREATE INDEX IF NOT EXISTS ix_ibpt_rates_lookup ON ibpt_rates(tenant_id, uf, code, snapshot_id);

-- Departamento Pessoal, benefícios, afastamentos, férias e fechamento do ponto.
CREATE TABLE IF NOT EXISTS employee_benefits (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, employee_id TEXT NOT NULL REFERENCES employees(id),
  benefit_type TEXT NOT NULL, provider TEXT, amount NUMERIC NOT NULL DEFAULT 0,
  starts_on TEXT NOT NULL, ends_on TEXT, state TEXT NOT NULL DEFAULT 'active', version INTEGER NOT NULL DEFAULT 1,
  metadata_json TEXT NOT NULL DEFAULT '{}', created_by TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS personnel_leaves (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, employee_id TEXT NOT NULL REFERENCES employees(id),
  leave_type TEXT NOT NULL, starts_on TEXT NOT NULL, ends_on TEXT NOT NULL, reason TEXT NOT NULL,
  deduct_payroll INTEGER NOT NULL DEFAULT 0, deduct_timekeeping INTEGER NOT NULL DEFAULT 1,
  document_id TEXT, state TEXT NOT NULL DEFAULT 'submitted', version INTEGER NOT NULL DEFAULT 1,
  requested_by TEXT NOT NULL, approved_by TEXT, approved_at TEXT, rejection_reason TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS vacation_periods (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, employee_id TEXT NOT NULL REFERENCES employees(id),
  accrual_start TEXT NOT NULL, accrual_end TEXT NOT NULL, scheduled_start TEXT NOT NULL, scheduled_end TEXT NOT NULL,
  days INTEGER NOT NULL, state TEXT NOT NULL DEFAULT 'scheduled', version INTEGER NOT NULL DEFAULT 1,
  approved_by TEXT, approved_at TEXT, cancellation_reason TEXT, created_by TEXT NOT NULL,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS timekeeping_adjustments (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, employee_id TEXT NOT NULL REFERENCES employees(id),
  time_entry_id TEXT REFERENCES time_entries(id), requested_event_type TEXT NOT NULL, requested_occurred_at TEXT NOT NULL,
  reason TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'submitted', version INTEGER NOT NULL DEFAULT 1,
  requested_by TEXT NOT NULL, reviewed_by TEXT, reviewed_at TEXT, review_reason TEXT,
  replacement_entry_id TEXT REFERENCES time_entries(id), created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS timekeeping_period_closures (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, competence TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'closed', version INTEGER NOT NULL DEFAULT 1,
  closed_by TEXT NOT NULL, closed_at TEXT NOT NULL, reopened_by TEXT, reopened_at TEXT, reopen_reason TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(tenant_id, competence)
);
CREATE INDEX IF NOT EXISTS ix_personnel_leaves_employee ON personnel_leaves(tenant_id, employee_id, starts_on, ends_on, state);
CREATE INDEX IF NOT EXISTS ix_vacation_periods_employee ON vacation_periods(tenant_id, employee_id, scheduled_start, scheduled_end, state);
CREATE INDEX IF NOT EXISTS ix_timekeeping_adjustments_employee ON timekeeping_adjustments(tenant_id, employee_id, state, created_at);

-- Operações avançadas de estoque, vendas, PDV, compras e patrimônio.
CREATE TABLE IF NOT EXISTS stock_transfers (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, from_warehouse TEXT NOT NULL, to_warehouse TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'completed', reason TEXT NOT NULL, created_by TEXT NOT NULL,
  created_at TEXT NOT NULL, completed_at TEXT
);
CREATE TABLE IF NOT EXISTS stock_transfer_items (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, stock_transfer_id TEXT NOT NULL REFERENCES stock_transfers(id),
  product_id TEXT NOT NULL REFERENCES products(id), quantity NUMERIC NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS inventory_counts (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, warehouse TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'draft',
  reason TEXT, created_by TEXT NOT NULL, approved_by TEXT, created_at TEXT NOT NULL, finalized_at TEXT
);
CREATE TABLE IF NOT EXISTS inventory_count_items (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, inventory_count_id TEXT NOT NULL REFERENCES inventory_counts(id),
  product_id TEXT NOT NULL REFERENCES products(id), expected_quantity NUMERIC NOT NULL, counted_quantity NUMERIC NOT NULL,
  difference NUMERIC NOT NULL, movement_id TEXT, created_at TEXT NOT NULL, UNIQUE(inventory_count_id, product_id)
);
CREATE TABLE IF NOT EXISTS sale_returns (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, sale_id TEXT NOT NULL REFERENCES sales(id),
  total_amount NUMERIC NOT NULL, refund_method TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'completed',
  reason TEXT NOT NULL, created_by TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sale_return_items (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, sale_return_id TEXT NOT NULL REFERENCES sale_returns(id),
  sale_item_id TEXT NOT NULL REFERENCES sale_items(id), product_id TEXT NOT NULL REFERENCES products(id),
  quantity NUMERIC NOT NULL, amount NUMERIC NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sale_refunds (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, sale_return_id TEXT NOT NULL REFERENCES sale_returns(id),
  method TEXT NOT NULL, amount NUMERIC NOT NULL, state TEXT NOT NULL, external_reference TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS cash_movements (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, cash_session_id TEXT NOT NULL REFERENCES cash_sessions(id),
  movement_type TEXT NOT NULL, amount NUMERIC NOT NULL, reason TEXT NOT NULL, created_by TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS purchase_receipts (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, purchase_order_id TEXT NOT NULL REFERENCES purchase_orders(id),
  state TEXT NOT NULL DEFAULT 'received', reason TEXT NOT NULL, created_by TEXT NOT NULL, received_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS purchase_receipt_items (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, purchase_receipt_id TEXT NOT NULL REFERENCES purchase_receipts(id),
  purchase_order_item_id TEXT NOT NULL REFERENCES purchase_order_items(id), product_id TEXT NOT NULL REFERENCES products(id),
  quantity NUMERIC NOT NULL, unit_cost NUMERIC NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS asset_events (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, asset_id TEXT NOT NULL REFERENCES assets(id),
  event_type TEXT NOT NULL, from_location TEXT, to_location TEXT, responsible_person_id TEXT REFERENCES people(id),
  cost NUMERIC, notes TEXT, state TEXT NOT NULL DEFAULT 'completed', occurred_at TEXT NOT NULL, created_by TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_stock_movements_product_time ON stock_movements(tenant_id,product_id,occurred_at);
CREATE INDEX IF NOT EXISTS ix_sale_returns_sale ON sale_returns(tenant_id,sale_id,created_at);
CREATE INDEX IF NOT EXISTS ix_asset_events_asset ON asset_events(tenant_id,asset_id,occurred_at);

-- Ciclo financeiro: reembolsos, renegociação e conciliação.
CREATE TABLE IF NOT EXISTS payment_refunds (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, payment_id TEXT NOT NULL REFERENCES payments(id),
  amount NUMERIC NOT NULL, method TEXT NOT NULL, reason TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'confirmed',
  external_reference TEXT, created_by TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS payment_refund_allocations (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, payment_refund_id TEXT NOT NULL REFERENCES payment_refunds(id),
  installment_id TEXT NOT NULL REFERENCES installments(id), amount NUMERIC NOT NULL, created_at TEXT NOT NULL,
  UNIQUE(payment_refund_id, installment_id)
);
CREATE TABLE IF NOT EXISTS financial_renegotiations (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, original_contract_id TEXT NOT NULL REFERENCES financial_contracts(id),
  new_contract_id TEXT REFERENCES financial_contracts(id), original_open_amount NUMERIC NOT NULL,
  new_total_amount NUMERIC NOT NULL, reason TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'completed',
  terms_json TEXT NOT NULL DEFAULT '{}', created_by TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_payment_refunds_payment ON payment_refunds(tenant_id,payment_id,created_at);
CREATE INDEX IF NOT EXISTS ix_renegotiations_contract ON financial_renegotiations(tenant_id,original_contract_id,created_at);

CREATE TABLE IF NOT EXISTS admission_candidate_events (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, candidate_id TEXT NOT NULL REFERENCES admission_candidates(id),
  event_type TEXT NOT NULL, from_state TEXT, to_state TEXT, reason TEXT, payload_json TEXT NOT NULL DEFAULT '{}',
  actor_id TEXT NOT NULL, occurred_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS enrollment_movements (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, enrollment_id TEXT NOT NULL REFERENCES enrollments(id),
  movement_type TEXT NOT NULL, from_state TEXT, to_state TEXT,
  from_unit_id TEXT, to_unit_id TEXT, from_class_group_id TEXT, to_class_group_id TEXT,
  effective_on TEXT NOT NULL, reason TEXT NOT NULL, payload_json TEXT NOT NULL DEFAULT '{}',
  actor_id TEXT NOT NULL, occurred_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_admission_candidate_events ON admission_candidate_events(tenant_id,candidate_id,occurred_at);
CREATE INDEX IF NOT EXISTS ix_enrollment_movements ON enrollment_movements(tenant_id,enrollment_id,effective_on,occurred_at);

CREATE TABLE IF NOT EXISTS canteen_locations (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, unit_id TEXT REFERENCES units(id), code TEXT NOT NULL, name TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id, code)
);
CREATE TABLE IF NOT EXISTS canteen_menus (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, canteen_location_id TEXT NOT NULL REFERENCES canteen_locations(id),
  name TEXT NOT NULL, starts_on TEXT, ends_on TEXT, state TEXT NOT NULL DEFAULT 'draft', version INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS canteen_menu_items (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, canteen_menu_id TEXT NOT NULL REFERENCES canteen_menus(id),
  product_id TEXT NOT NULL REFERENCES products(id), price_override NUMERIC, available_from TEXT, available_until TEXT,
  state TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL,
  UNIQUE(canteen_menu_id, product_id)
);
CREATE TABLE IF NOT EXISTS student_wallets (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, student_id TEXT NOT NULL REFERENCES students(id),
  balance NUMERIC NOT NULL DEFAULT 0, daily_limit NUMERIC, weekly_limit NUMERIC,
  state TEXT NOT NULL DEFAULT 'active', version INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id, student_id)
);
CREATE TABLE IF NOT EXISTS wallet_transactions (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, wallet_id TEXT NOT NULL REFERENCES student_wallets(id),
  transaction_type TEXT NOT NULL, amount NUMERIC NOT NULL, balance_before NUMERIC NOT NULL, balance_after NUMERIC NOT NULL,
  reference_type TEXT, reference_id TEXT, reason TEXT, created_by TEXT, idempotency_key TEXT, created_at TEXT NOT NULL,
  UNIQUE(tenant_id, idempotency_key)
);
CREATE TABLE IF NOT EXISTS student_food_policies (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, student_id TEXT NOT NULL REFERENCES students(id),
  blocked_allergens_json TEXT NOT NULL DEFAULT '[]', blocked_product_ids_json TEXT NOT NULL DEFAULT '[]',
  daily_limit NUMERIC, weekly_limit NUMERIC, purchase_start_time TEXT, purchase_end_time TEXT,
  notes TEXT, state TEXT NOT NULL DEFAULT 'active', version INTEGER NOT NULL DEFAULT 1,
  created_by TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id, student_id)
);
CREATE TABLE IF NOT EXISTS canteen_subsidies (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, student_id TEXT NOT NULL REFERENCES students(id),
  subsidy_type TEXT NOT NULL, amount NUMERIC, percentage NUMERIC, valid_from TEXT NOT NULL, valid_until TEXT,
  reason TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'active', created_by TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_wallet_transactions_wallet ON wallet_transactions(tenant_id,wallet_id,created_at);
CREATE INDEX IF NOT EXISTS ix_food_policy_student ON student_food_policies(tenant_id,student_id,state);
CREATE INDEX IF NOT EXISTS ix_canteen_menu_dates ON canteen_menus(tenant_id,canteen_location_id,state,starts_on,ends_on);

-- Pedagógico: avaliações, notas, recuperação e fechamento por período.
CREATE TABLE IF NOT EXISTS grading_policies (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, academic_year_id TEXT NOT NULL REFERENCES academic_years(id),
  class_group_id TEXT REFERENCES class_groups(id), component_id TEXT REFERENCES curriculum_components(id),
  name TEXT NOT NULL, calculation_method TEXT NOT NULL DEFAULT 'weighted_average', max_score NUMERIC NOT NULL DEFAULT 10,
  passing_score NUMERIC NOT NULL DEFAULT 6, attendance_minimum NUMERIC NOT NULL DEFAULT 75,
  rounding_precision INTEGER NOT NULL DEFAULT 2, recovery_strategy TEXT NOT NULL DEFAULT 'replace_if_higher',
  settings_json TEXT NOT NULL DEFAULT '{}', effective_from TEXT NOT NULL, effective_until TEXT,
  state TEXT NOT NULL DEFAULT 'active', version INTEGER NOT NULL DEFAULT 1, created_by TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_grading_policies_scope ON grading_policies(tenant_id,academic_year_id,class_group_id,component_id,state,effective_from);
CREATE TABLE IF NOT EXISTS assessments (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, academic_period_id TEXT NOT NULL REFERENCES academic_periods(id),
  class_group_id TEXT NOT NULL REFERENCES class_groups(id), component_id TEXT NOT NULL REFERENCES curriculum_components(id),
  grading_policy_id TEXT REFERENCES grading_policies(id), title TEXT NOT NULL, assessment_type TEXT NOT NULL DEFAULT 'exam',
  weight NUMERIC NOT NULL DEFAULT 1, max_score NUMERIC NOT NULL DEFAULT 10, due_on TEXT, state TEXT NOT NULL DEFAULT 'draft',
  version INTEGER NOT NULL DEFAULT 1, created_by TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_assessments_scope ON assessments(tenant_id,academic_period_id,class_group_id,component_id,state);
CREATE TABLE IF NOT EXISTS assessment_grades (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, assessment_id TEXT NOT NULL REFERENCES assessments(id),
  enrollment_id TEXT NOT NULL REFERENCES enrollments(id), score NUMERIC, concept TEXT, status TEXT NOT NULL DEFAULT 'graded',
  feedback TEXT, version INTEGER NOT NULL DEFAULT 1, graded_by TEXT NOT NULL, graded_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id,assessment_id,enrollment_id)
);
CREATE INDEX IF NOT EXISTS ix_assessment_grades_enrollment ON assessment_grades(tenant_id,enrollment_id,assessment_id);
CREATE TABLE IF NOT EXISTS assessment_grade_events (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, assessment_grade_id TEXT NOT NULL REFERENCES assessment_grades(id),
  event_type TEXT NOT NULL, before_json TEXT NOT NULL DEFAULT '{}', after_json TEXT NOT NULL DEFAULT '{}',
  reason TEXT, actor_id TEXT NOT NULL, occurred_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS period_results (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, academic_period_id TEXT NOT NULL REFERENCES academic_periods(id),
  class_group_id TEXT NOT NULL REFERENCES class_groups(id), component_id TEXT NOT NULL REFERENCES curriculum_components(id),
  enrollment_id TEXT NOT NULL REFERENCES enrollments(id), grading_policy_id TEXT NOT NULL REFERENCES grading_policies(id),
  average_score NUMERIC NOT NULL DEFAULT 0, recovery_score NUMERIC, final_score NUMERIC NOT NULL DEFAULT 0,
  attendance_percentage NUMERIC NOT NULL DEFAULT 100, outcome TEXT NOT NULL DEFAULT 'pending', state TEXT NOT NULL DEFAULT 'open',
  calculation_json TEXT NOT NULL DEFAULT '{}', version INTEGER NOT NULL DEFAULT 1, calculated_at TEXT NOT NULL,
  closed_at TEXT, closed_by TEXT, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id,academic_period_id,class_group_id,component_id,enrollment_id)
);
CREATE INDEX IF NOT EXISTS ix_period_results_student ON period_results(tenant_id,enrollment_id,academic_period_id,component_id);
CREATE TABLE IF NOT EXISTS grade_period_closures (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, academic_period_id TEXT NOT NULL REFERENCES academic_periods(id),
  class_group_id TEXT NOT NULL REFERENCES class_groups(id), component_id TEXT NOT NULL REFERENCES curriculum_components(id),
  state TEXT NOT NULL DEFAULT 'closed', version INTEGER NOT NULL DEFAULT 1, reason TEXT NOT NULL,
  closed_by TEXT NOT NULL, closed_at TEXT NOT NULL, reopened_by TEXT, reopened_at TEXT, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id,academic_period_id,class_group_id,component_id)
);

-- Educação infantil e progressão técnico/superior.
CREATE TABLE IF NOT EXISTS early_childhood_daily_records (
  id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,student_id TEXT NOT NULL REFERENCES students(id),unit_id TEXT NOT NULL REFERENCES units(id),
  record_date TEXT NOT NULL,meals_json TEXT NOT NULL DEFAULT '[]',sleep_json TEXT NOT NULL DEFAULT '{}',hygiene_json TEXT NOT NULL DEFAULT '[]',
  diaper_changes_json TEXT NOT NULL DEFAULT '[]',mood TEXT,development_notes TEXT,authorized_photos_json TEXT NOT NULL DEFAULT '[]',
  state TEXT NOT NULL DEFAULT 'active',version INTEGER NOT NULL DEFAULT 1,created_by TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
  UNIQUE(tenant_id,student_id,record_date)
);
CREATE INDEX IF NOT EXISTS ix_early_childhood_daily_date ON early_childhood_daily_records(tenant_id,unit_id,record_date);
CREATE TABLE IF NOT EXISTS student_pickup_records (
  id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,student_id TEXT NOT NULL REFERENCES students(id),guardian_id TEXT REFERENCES guardians(id),
  pickup_person_name TEXT NOT NULL,relationship TEXT,identity_document_masked TEXT,released_at TEXT NOT NULL,released_by TEXT NOT NULL,
  notes TEXT,created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_student_pickup_student ON student_pickup_records(tenant_id,student_id,released_at);
CREATE TABLE IF NOT EXISTS component_prerequisites (
  id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,component_id TEXT NOT NULL REFERENCES curriculum_components(id),
  prerequisite_component_id TEXT NOT NULL REFERENCES curriculum_components(id),minimum_final_score NUMERIC,state TEXT NOT NULL DEFAULT 'active',created_at TEXT NOT NULL,
  UNIQUE(tenant_id,component_id,prerequisite_component_id)
);
CREATE TABLE IF NOT EXISTS student_component_completions (
  id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,enrollment_id TEXT NOT NULL REFERENCES enrollments(id),component_id TEXT NOT NULL REFERENCES curriculum_components(id),
  source_type TEXT NOT NULL,source_reference_id TEXT,final_score NUMERIC,credits_awarded NUMERIC,workload_hours_awarded NUMERIC,
  completed_on TEXT NOT NULL,state TEXT NOT NULL DEFAULT 'approved',reason TEXT,approved_by TEXT NOT NULL,created_at TEXT NOT NULL,
  UNIQUE(tenant_id,enrollment_id,component_id,state)
);
CREATE TABLE IF NOT EXISTS internships (
  id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,enrollment_id TEXT NOT NULL REFERENCES enrollments(id),organization_name TEXT NOT NULL,
  supervisor_name TEXT,advisor_employee_id TEXT REFERENCES employees(id),starts_on TEXT NOT NULL,ends_on TEXT,required_hours NUMERIC NOT NULL DEFAULT 0,
  completed_hours NUMERIC NOT NULL DEFAULT 0,state TEXT NOT NULL DEFAULT 'draft',version INTEGER NOT NULL DEFAULT 1,notes TEXT,
  created_by TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS internship_hour_logs (
  id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,internship_id TEXT NOT NULL REFERENCES internships(id),activity_date TEXT NOT NULL,hours NUMERIC NOT NULL,
  description TEXT NOT NULL,state TEXT NOT NULL DEFAULT 'approved',recorded_by TEXT NOT NULL,created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS complementary_activities (
  id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,enrollment_id TEXT NOT NULL REFERENCES enrollments(id),category TEXT NOT NULL,title TEXT NOT NULL,
  requested_hours NUMERIC NOT NULL,approved_hours NUMERIC NOT NULL DEFAULT 0,evidence_document_id TEXT REFERENCES documents(id),
  state TEXT NOT NULL DEFAULT 'submitted',review_notes TEXT,submitted_by TEXT NOT NULL,reviewed_by TEXT,submitted_at TEXT NOT NULL,reviewed_at TEXT
);
CREATE TABLE IF NOT EXISTS theses (
  id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,enrollment_id TEXT NOT NULL REFERENCES enrollments(id),title TEXT NOT NULL,
  advisor_employee_id TEXT REFERENCES employees(id),coadvisor_name TEXT,state TEXT NOT NULL DEFAULT 'proposal',grade NUMERIC,
  defense_at TEXT,abstract TEXT,document_id TEXT REFERENCES documents(id),version INTEGER NOT NULL DEFAULT 1,created_by TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS thesis_events (
  id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,thesis_id TEXT NOT NULL REFERENCES theses(id),event_type TEXT NOT NULL,state TEXT NOT NULL,
  details_json TEXT NOT NULL DEFAULT '{}',actor_id TEXT NOT NULL,occurred_at TEXT NOT NULL
);

-- Compliance / LGPD
CREATE TABLE IF NOT EXISTS privacy_notices (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, code TEXT NOT NULL, title TEXT NOT NULL,
  version INTEGER NOT NULL, content TEXT NOT NULL, effective_from TEXT NOT NULL, effective_until TEXT,
  state TEXT NOT NULL DEFAULT 'draft', sha256 TEXT NOT NULL, created_by TEXT NOT NULL,
  published_by TEXT, published_at TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id, code, version)
);
CREATE TABLE IF NOT EXISTS processing_activities (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, code TEXT NOT NULL, name TEXT NOT NULL,
  purpose TEXT NOT NULL, legal_basis TEXT NOT NULL, privacy_notice_code TEXT, data_categories_json TEXT NOT NULL DEFAULT '[]',
  data_subjects_json TEXT NOT NULL DEFAULT '[]', recipients_json TEXT NOT NULL DEFAULT '[]',
  international_transfer INTEGER NOT NULL DEFAULT 0, retention_rule TEXT, security_measures_json TEXT NOT NULL DEFAULT '[]',
  owner_department TEXT, state TEXT NOT NULL DEFAULT 'active', version INTEGER NOT NULL DEFAULT 1,
  created_by TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id, code, version)
);
CREATE TABLE IF NOT EXISTS consent_records (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, subject_person_id TEXT NOT NULL REFERENCES people(id),
  granted_by_person_id TEXT NOT NULL REFERENCES people(id), purpose_code TEXT NOT NULL,
  legal_basis TEXT NOT NULL DEFAULT 'consent', privacy_notice_id TEXT REFERENCES privacy_notices(id),
  channel TEXT NOT NULL, evidence_json TEXT NOT NULL DEFAULT '{}', state TEXT NOT NULL DEFAULT 'granted',
  granted_at TEXT NOT NULL, revoked_at TEXT, revoked_by TEXT, revocation_reason TEXT,
  created_by TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_consent_subject ON consent_records(tenant_id,subject_person_id,purpose_code,state);
CREATE TABLE IF NOT EXISTS data_subject_requests (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, protocol TEXT NOT NULL,
  subject_person_id TEXT NOT NULL REFERENCES people(id), requester_person_id TEXT NOT NULL REFERENCES people(id),
  request_type TEXT NOT NULL, description TEXT, state TEXT NOT NULL DEFAULT 'submitted', priority TEXT NOT NULL DEFAULT 'normal',
  due_at TEXT, decision_reason TEXT, assigned_to TEXT, export_storage_key TEXT, export_sha256 TEXT,
  export_bytes INTEGER, exported_at TEXT, fulfilled_at TEXT, created_by TEXT NOT NULL,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(tenant_id,protocol)
);
CREATE TABLE IF NOT EXISTS data_subject_request_events (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, request_id TEXT NOT NULL REFERENCES data_subject_requests(id),
  event_type TEXT NOT NULL, from_state TEXT, to_state TEXT, details_json TEXT NOT NULL DEFAULT '{}',
  actor_id TEXT NOT NULL, occurred_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS retention_policies (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, data_category TEXT NOT NULL, purpose_code TEXT,
  retention_days INTEGER NOT NULL, disposition TEXT NOT NULL, legal_basis TEXT NOT NULL,
  starts_on TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'active', version INTEGER NOT NULL DEFAULT 1,
  created_by TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS legal_holds (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, person_id TEXT REFERENCES people(id),
  aggregate_type TEXT, aggregate_id TEXT, reason TEXT NOT NULL, starts_at TEXT NOT NULL, ends_at TEXT,
  state TEXT NOT NULL DEFAULT 'active', created_by TEXT NOT NULL, released_by TEXT, released_at TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS government_validation_runs (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, layout_id TEXT NOT NULL REFERENCES government_export_layouts(id),
  reference_period TEXT NOT NULL, direction TEXT NOT NULL, state TEXT NOT NULL,
  record_count INTEGER NOT NULL DEFAULT 0, error_count INTEGER NOT NULL DEFAULT 0, warning_count INTEGER NOT NULL DEFAULT 0,
  source_sha256 TEXT, created_by TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS government_validation_issues (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, run_id TEXT NOT NULL REFERENCES government_validation_runs(id),
  row_number INTEGER, field_code TEXT, severity TEXT NOT NULL, code TEXT NOT NULL, message TEXT NOT NULL,
  source_ref TEXT, state TEXT NOT NULL DEFAULT 'open', resolved_by TEXT, resolved_at TEXT, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_government_validation_issues_run ON government_validation_issues(tenant_id, run_id, severity, state);
CREATE TABLE IF NOT EXISTS government_imports (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, layout_id TEXT NOT NULL REFERENCES government_export_layouts(id),
  validation_run_id TEXT NOT NULL REFERENCES government_validation_runs(id), reference_period TEXT NOT NULL,
  original_filename TEXT NOT NULL, state TEXT NOT NULL, row_count INTEGER NOT NULL DEFAULT 0,
  accepted_count INTEGER NOT NULL DEFAULT 0, rejected_count INTEGER NOT NULL DEFAULT 0,
  sha256 TEXT NOT NULL, storage_key TEXT NOT NULL, created_by TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS government_transmissions (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, export_id TEXT NOT NULL REFERENCES government_exports(id),
  connection_id TEXT REFERENCES integration_connections(id), environment TEXT NOT NULL,
  state TEXT NOT NULL, idempotency_key TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
  protocol TEXT, receipt_json TEXT, provider_status TEXT, last_error TEXT,
  created_by TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, submitted_at TEXT, completed_at TEXT,
  UNIQUE(tenant_id, idempotency_key)
);
CREATE TABLE IF NOT EXISTS government_transmission_events (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, transmission_id TEXT NOT NULL REFERENCES government_transmissions(id),
  event_type TEXT NOT NULL, from_state TEXT, to_state TEXT, details_json TEXT NOT NULL DEFAULT '{}',
  actor_id TEXT NOT NULL, occurred_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS admission_campaigns (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, code TEXT NOT NULL, name TEXT NOT NULL,
  program_id TEXT REFERENCES programs(id), academic_year_id TEXT REFERENCES academic_years(id),
  starts_on TEXT NOT NULL, ends_on TEXT, channels_json TEXT NOT NULL DEFAULT '[]', budget NUMERIC,
  state TEXT NOT NULL DEFAULT 'draft', created_by TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id, code)
);
CREATE TABLE IF NOT EXISTS admission_leads (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, campaign_id TEXT REFERENCES admission_campaigns(id), person_id TEXT REFERENCES people(id),
  full_name TEXT NOT NULL, email TEXT, phone TEXT, desired_program_id TEXT REFERENCES programs(id), desired_academic_year_id TEXT REFERENCES academic_years(id),
  source TEXT, external_ref TEXT, consent_at TEXT, state TEXT NOT NULL DEFAULT 'new', owner_user_id TEXT, notes TEXT,
  converted_candidate_id TEXT REFERENCES admission_candidates(id), created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id, source, external_ref)
);
CREATE TABLE IF NOT EXISTS admission_processes (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, code TEXT NOT NULL, name TEXT NOT NULL,
  program_id TEXT NOT NULL REFERENCES programs(id), academic_year_id TEXT NOT NULL REFERENCES academic_years(id),
  applications_open_at TEXT, applications_close_at TEXT, seats INTEGER, ranking_method TEXT NOT NULL DEFAULT 'weighted_sum',
  state TEXT NOT NULL DEFAULT 'draft', created_by TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id, code)
);
CREATE TABLE IF NOT EXISTS admission_assessments (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, process_id TEXT NOT NULL REFERENCES admission_processes(id),
  code TEXT NOT NULL, name TEXT NOT NULL, assessment_type TEXT NOT NULL, weight NUMERIC NOT NULL DEFAULT 1,
  max_score NUMERIC NOT NULL DEFAULT 100, scheduled_at TEXT, state TEXT NOT NULL DEFAULT 'active',
  created_by TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id, process_id, code)
);
CREATE TABLE IF NOT EXISTS admission_applications (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, process_id TEXT NOT NULL REFERENCES admission_processes(id),
  candidate_id TEXT NOT NULL REFERENCES admission_candidates(id), application_number TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'applied', final_score NUMERIC, rank_position INTEGER,
  applied_at TEXT NOT NULL, selected_at TEXT, rejected_at TEXT, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id, process_id, candidate_id), UNIQUE(tenant_id, application_number)
);
CREATE TABLE IF NOT EXISTS admission_assessment_results (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, application_id TEXT NOT NULL REFERENCES admission_applications(id),
  assessment_id TEXT NOT NULL REFERENCES admission_assessments(id), score NUMERIC NOT NULL, outcome TEXT,
  notes TEXT, version INTEGER NOT NULL DEFAULT 1, created_by TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id, application_id, assessment_id)
);
CREATE TABLE IF NOT EXISTS admission_vacancy_reservations (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, application_id TEXT NOT NULL REFERENCES admission_applications(id),
  candidate_id TEXT NOT NULL REFERENCES admission_candidates(id), class_group_id TEXT NOT NULL REFERENCES class_groups(id),
  expires_at TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'reserved', consumed_enrollment_id TEXT REFERENCES enrollments(id),
  reason TEXT, created_by TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_admission_leads_state ON admission_leads(tenant_id,state,created_at);
CREATE INDEX IF NOT EXISTS ix_admission_applications_process ON admission_applications(tenant_id,process_id,state,rank_position);
CREATE INDEX IF NOT EXISTS ix_admission_reservations_capacity ON admission_vacancy_reservations(tenant_id,class_group_id,state,expires_at);
