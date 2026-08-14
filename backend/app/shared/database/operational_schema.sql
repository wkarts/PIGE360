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
  catalog_id TEXT, service_type TEXT NOT NULL DEFAULT 'other', recurrence_type TEXT NOT NULL DEFAULT 'one_time',
  unit_of_measure TEXT NOT NULL DEFAULT 'unit', default_duration_minutes INTEGER, cost_center_id TEXT,
  taxable INTEGER NOT NULL DEFAULT 1, metadata_json TEXT NOT NULL DEFAULT '{}', institution_id TEXT, unit_id TEXT,
  version INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id, code)
);
CREATE TABLE IF NOT EXISTS service_orders (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, enrollment_id TEXT REFERENCES enrollments(id),
  responsible_guardian_id TEXT REFERENCES guardians(id), competence TEXT, state TEXT NOT NULL DEFAULT 'draft',
  total_amount NUMERIC NOT NULL DEFAULT 0, financial_contract_id TEXT REFERENCES financial_contracts(id),
  fiscal_document_id TEXT, order_number TEXT, subscriber_person_id TEXT REFERENCES people(id), subscription_id TEXT,
  competence_id TEXT, cost_center_id TEXT, currency TEXT NOT NULL DEFAULT 'BRL', subtotal NUMERIC NOT NULL DEFAULT 0,
  discount_amount NUMERIC NOT NULL DEFAULT 0, due_date TEXT, installment_count INTEGER NOT NULL DEFAULT 1,
  charge_id TEXT, fiscal_status TEXT NOT NULL DEFAULT 'pending', notes TEXT, confirmed_at TEXT, confirmed_by TEXT,
  started_at TEXT, completed_at TEXT, cancelled_at TEXT, cancellation_reason TEXT, institution_id TEXT, unit_id TEXT,
  version INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id, order_number)
);
CREATE TABLE IF NOT EXISTS service_order_items (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, service_order_id TEXT NOT NULL REFERENCES service_orders(id),
  service_id TEXT NOT NULL REFERENCES services(id), quantity NUMERIC NOT NULL, unit_price NUMERIC NOT NULL,
  total_amount NUMERIC NOT NULL, variant_id TEXT, description TEXT, discount_amount NUMERIC NOT NULL DEFAULT 0,
  competence_start TEXT, competence_end TEXT, fiscal_profile_snapshot_json TEXT NOT NULL DEFAULT '{}',
  execution_status TEXT NOT NULL DEFAULT 'pending', executed_quantity NUMERIC NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS service_receipts (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, receipt_number TEXT NOT NULL,
  service_order_id TEXT NOT NULL REFERENCES service_orders(id), charge_id TEXT NOT NULL REFERENCES charges(id),
  payment_id TEXT NOT NULL REFERENCES payments(id), currency TEXT NOT NULL DEFAULT 'BRL', amount NUMERIC NOT NULL,
  payment_method TEXT NOT NULL, external_reference TEXT, recipient_name TEXT, recipient_document TEXT,
  state TEXT NOT NULL DEFAULT 'issued', document_storage_key TEXT NOT NULL, document_sha256 TEXT NOT NULL,
  snapshot_json TEXT NOT NULL DEFAULT '{}', issued_at TEXT NOT NULL, issued_by TEXT NOT NULL,
  voided_at TEXT, voided_by TEXT, void_reason TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id, receipt_number)
);
CREATE INDEX IF NOT EXISTS ix_service_receipts_order ON service_receipts(tenant_id,service_order_id,state,issued_at);
CREATE INDEX IF NOT EXISTS ix_service_receipts_payment ON service_receipts(tenant_id,payment_id,state,issued_at);
CREATE UNIQUE INDEX IF NOT EXISTS ux_service_receipts_active_payment ON service_receipts(tenant_id,service_order_id,payment_id) WHERE state='issued';

CREATE TABLE IF NOT EXISTS products (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, sku TEXT NOT NULL, barcode TEXT, name TEXT NOT NULL,
  product_type TEXT NOT NULL DEFAULT 'product', school_catalog_category TEXT NOT NULL DEFAULT 'general', ncm TEXT, cest TEXT, unit TEXT NOT NULL DEFAULT 'UN',
  cost NUMERIC NOT NULL DEFAULT 0, sale_price NUMERIC NOT NULL DEFAULT 0, fiscal_profile_json TEXT NOT NULL DEFAULT '{}',
  allergen_json TEXT NOT NULL DEFAULT '[]', restriction_json TEXT NOT NULL DEFAULT '{}', state TEXT NOT NULL DEFAULT 'active',
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(tenant_id, sku), UNIQUE(tenant_id, barcode)
);
CREATE INDEX IF NOT EXISTS ix_products_school_catalog_category ON products(tenant_id, school_catalog_category, state);
CREATE TABLE IF NOT EXISTS stock_balances (
  tenant_id TEXT NOT NULL, product_id TEXT NOT NULL REFERENCES products(id), warehouse TEXT NOT NULL DEFAULT 'default',
  quantity NUMERIC NOT NULL DEFAULT 0, reserved NUMERIC NOT NULL DEFAULT 0, updated_at TEXT NOT NULL,
  PRIMARY KEY(tenant_id, product_id, warehouse)
);
CREATE TABLE IF NOT EXISTS stock_movements (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, product_id TEXT NOT NULL REFERENCES products(id), warehouse TEXT NOT NULL DEFAULT 'default',
  movement_type TEXT NOT NULL, quantity NUMERIC NOT NULL, unit_cost NUMERIC, reference_type TEXT, reference_id TEXT,
  reason TEXT, occurred_at TEXT NOT NULL, created_by TEXT, lot_id TEXT, balance_after NUMERIC
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
  email TEXT, phone TEXT, state TEXT NOT NULL DEFAULT 'active', code TEXT, rating NUMERIC,
  payment_terms_json TEXT NOT NULL DEFAULT '{}', fiscal_profile_json TEXT NOT NULL DEFAULT '{}', notes TEXT,
  institution_id TEXT, unit_id TEXT, version INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id, cnpj), UNIQUE(tenant_id, code)
);
CREATE TABLE IF NOT EXISTS purchase_orders (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, supplier_id TEXT NOT NULL REFERENCES suppliers(id),
  order_number TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'draft', total_amount NUMERIC NOT NULL DEFAULT 0,
  expected_on TEXT, received_at TEXT, warehouse_id TEXT NOT NULL DEFAULT 'default', quotation_id TEXT,
  requisition_id TEXT, currency TEXT NOT NULL DEFAULT 'BRL', subtotal NUMERIC NOT NULL DEFAULT 0,
  freight_amount NUMERIC NOT NULL DEFAULT 0, discount_amount NUMERIC NOT NULL DEFAULT 0, notes TEXT,
  approved_at TEXT, approved_by TEXT, closed_at TEXT, institution_id TEXT, unit_id TEXT, version INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(tenant_id, order_number)
);
CREATE TABLE IF NOT EXISTS purchase_order_items (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, purchase_order_id TEXT NOT NULL REFERENCES purchase_orders(id),
  product_id TEXT NOT NULL REFERENCES products(id), quantity NUMERIC NOT NULL, unit_cost NUMERIC NOT NULL,
  received_quantity NUMERIC NOT NULL DEFAULT 0, returned_quantity NUMERIC NOT NULL DEFAULT 0,
  discount_amount NUMERIC NOT NULL DEFAULT 0, total_amount NUMERIC NOT NULL DEFAULT 0,
  fiscal_profile_snapshot_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS assets (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, asset_number TEXT NOT NULL, description TEXT NOT NULL,
  acquisition_date TEXT, acquisition_cost NUMERIC, location TEXT, responsible_person_id TEXT REFERENCES people(id),
  state TEXT NOT NULL DEFAULT 'active', tag TEXT, name TEXT, location_id TEXT, product_id TEXT,
  receipt_item_id TEXT, serial_number TEXT, useful_life_months INTEGER, residual_value NUMERIC NOT NULL DEFAULT 0,
  accumulated_depreciation NUMERIC NOT NULL DEFAULT 0, warranty_until TEXT, metadata_json TEXT NOT NULL DEFAULT '{}',
  institution_id TEXT, unit_id TEXT, version INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id, asset_number), UNIQUE(tenant_id, tag)
);

CREATE TABLE IF NOT EXISTS fiscal_profiles (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, establishment_name TEXT NOT NULL, cnpj TEXT NOT NULL,
  tax_regime TEXT NOT NULL, uf TEXT NOT NULL, municipality_code TEXT, environment TEXT NOT NULL DEFAULT 'homologation',
  provider_connection_id TEXT REFERENCES integration_connections(id),
  state TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id, cnpj)
);
CREATE TABLE IF NOT EXISTS fiscal_contexts (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, code TEXT NOT NULL, establishment_name TEXT NOT NULL,
  legal_name TEXT, cnpj TEXT NOT NULL, institution_id TEXT REFERENCES institutions(id), unit_id TEXT REFERENCES units(id),
  state_registration TEXT, municipal_registration TEXT,
  provider_connection_id TEXT REFERENCES integration_connections(id), metadata_json TEXT NOT NULL DEFAULT '{}',
  state TEXT NOT NULL DEFAULT 'active', active_version_id TEXT,
  latest_version_number INTEGER NOT NULL DEFAULT 0, version INTEGER NOT NULL DEFAULT 1,
  created_by TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id,code), UNIQUE(tenant_id,cnpj)
);
CREATE TABLE IF NOT EXISTS fiscal_context_versions (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, fiscal_context_id TEXT NOT NULL REFERENCES fiscal_contexts(id),
  version_number INTEGER NOT NULL, tax_regime TEXT NOT NULL, uf TEXT NOT NULL, municipality_code TEXT NOT NULL,
  valid_from TEXT NOT NULL, valid_until TEXT, environment TEXT NOT NULL DEFAULT 'homologation',
  rtc_mode TEXT NOT NULL DEFAULT 'simulation_only', layout_version TEXT, schema_version TEXT,
  technical_note_version TEXT, ruleset_version TEXT, configuration_json TEXT NOT NULL DEFAULT '{}', notes TEXT,
  state TEXT NOT NULL DEFAULT 'draft', published_at TEXT, published_by TEXT,
  superseded_by_version_id TEXT REFERENCES fiscal_context_versions(id), version INTEGER NOT NULL DEFAULT 1,
  created_by TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id,fiscal_context_id,version_number)
);
CREATE TABLE IF NOT EXISTS fiscal_context_operation_scopes (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL,
  fiscal_context_version_id TEXT NOT NULL REFERENCES fiscal_context_versions(id),
  operation_type TEXT NOT NULL, item_kind TEXT NOT NULL DEFAULT 'any',
  recipient_scope TEXT NOT NULL DEFAULT 'any', document_type TEXT NOT NULL DEFAULT 'any', created_at TEXT NOT NULL,
  UNIQUE(tenant_id,fiscal_context_version_id,operation_type,item_kind,recipient_scope,document_type)
);
CREATE INDEX IF NOT EXISTS ix_fiscal_contexts_scope
  ON fiscal_contexts(tenant_id,state,institution_id,unit_id,cnpj);
CREATE INDEX IF NOT EXISTS ix_fiscal_context_versions_effective
  ON fiscal_context_versions(tenant_id,fiscal_context_id,state,valid_from,valid_until);
CREATE INDEX IF NOT EXISTS ix_fiscal_context_scopes_resolution
  ON fiscal_context_operation_scopes(tenant_id,operation_type,item_kind,recipient_scope,document_type);

CREATE TABLE IF NOT EXISTS fiscal_rules (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, fiscal_profile_id TEXT NOT NULL REFERENCES fiscal_profiles(id),
  operation_type TEXT NOT NULL, item_kind TEXT NOT NULL, classification_key TEXT,
  effective_from TEXT NOT NULL, effective_until TEXT, rules_json TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'active', version INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS fiscal_documents (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, fiscal_profile_id TEXT REFERENCES fiscal_profiles(id),
  fiscal_context_id TEXT REFERENCES fiscal_contexts(id),
  fiscal_context_version_id TEXT REFERENCES fiscal_context_versions(id),
  fiscal_context_snapshot_json TEXT NOT NULL DEFAULT '{}',
  document_type TEXT NOT NULL, source_type TEXT NOT NULL, source_id TEXT NOT NULL, environment TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'requested', access_key TEXT, protocol TEXT, number TEXT, series TEXT,
  provider_connection_id TEXT REFERENCES integration_connections(id), provider_document_id TEXT, provider_status TEXT NOT NULL DEFAULT 'not_configured',
  attempts INTEGER NOT NULL DEFAULT 0, last_attempt_at TEXT,
  totals_json TEXT NOT NULL DEFAULT '{}', request_json TEXT NOT NULL DEFAULT '{}', response_json TEXT NOT NULL DEFAULT '{}',
  xml_storage_key TEXT, pdf_storage_key TEXT, xml_sha256 TEXT, error_code TEXT, error_message TEXT,
  replacement_of_document_id TEXT, substituted_by_document_id TEXT, contingency_mode TEXT,
  delivery_policy_id TEXT, retry_count INTEGER NOT NULL DEFAULT 0, next_retry_at TEXT,
  authorized_at TEXT, cancelled_at TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(tenant_id, document_type, source_type, source_id)
);
CREATE TABLE IF NOT EXISTS fiscal_document_events (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, fiscal_document_id TEXT NOT NULL REFERENCES fiscal_documents(id),
  event_type TEXT NOT NULL, state TEXT NOT NULL, provider_connection_id TEXT REFERENCES integration_connections(id),
  provider_event_id TEXT, payload_json TEXT NOT NULL DEFAULT '{}', xml_storage_key TEXT, xml_sha256 TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fiscal_document_events_document ON fiscal_document_events(tenant_id,fiscal_document_id,created_at);


-- 0038: ciclo de vida de documentos fiscais e providers condicionais.
CREATE TABLE IF NOT EXISTS fiscal_certificate_metadata (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, certificate_type TEXT NOT NULL DEFAULT 'a1',
  subject_name TEXT NOT NULL, subject_document TEXT, serial_number TEXT NOT NULL, issuer_name TEXT NOT NULL,
  valid_from TEXT NOT NULL, valid_until TEXT NOT NULL, fingerprint_sha256 TEXT NOT NULL, secret_ref TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active', metadata_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id,fingerprint_sha256)
);
CREATE TABLE IF NOT EXISTS fiscal_provider_configurations (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, provider_code TEXT NOT NULL, display_name TEXT NOT NULL,
  document_type TEXT NOT NULL, environment TEXT NOT NULL DEFAULT 'homologation', endpoint_url TEXT, secret_ref TEXT,
  certificate_metadata_id TEXT REFERENCES fiscal_certificate_metadata(id), capabilities_json TEXT NOT NULL DEFAULT '[]',
  settings_json TEXT NOT NULL DEFAULT '{}', enabled INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'not_configured',
  last_health_status TEXT NOT NULL DEFAULT 'not_checked', last_health_at TEXT, last_health_detail TEXT,
  webhook_tolerance_seconds INTEGER NOT NULL DEFAULT 300, version INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id,provider_code,document_type,environment)
);
CREATE TABLE IF NOT EXISTS fiscal_document_attempts (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, fiscal_document_id TEXT NOT NULL REFERENCES fiscal_documents(id),
  provider_connection_id TEXT, operation TEXT NOT NULL, attempt_number INTEGER NOT NULL, state TEXT NOT NULL,
  request_sha256 TEXT NOT NULL, request_json TEXT NOT NULL DEFAULT '{}', response_json TEXT NOT NULL DEFAULT '{}',
  error_code TEXT, retryable INTEGER NOT NULL DEFAULT 0, started_at TEXT NOT NULL, finished_at TEXT, created_at TEXT NOT NULL,
  UNIQUE(tenant_id,fiscal_document_id,operation,attempt_number)
);
CREATE TABLE IF NOT EXISTS fiscal_document_artifacts (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, fiscal_document_id TEXT NOT NULL REFERENCES fiscal_documents(id),
  artifact_type TEXT NOT NULL, content_type TEXT NOT NULL, storage_key TEXT NOT NULL, sha256 TEXT NOT NULL,
  bytes_count INTEGER NOT NULL, provider_event_id TEXT, created_at TEXT NOT NULL,
  UNIQUE(tenant_id,fiscal_document_id,artifact_type,sha256)
);
CREATE TABLE IF NOT EXISTS fiscal_inutilization_requests (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, fiscal_profile_id TEXT NOT NULL,
  provider_configuration_id TEXT NOT NULL REFERENCES fiscal_provider_configurations(id), document_type TEXT NOT NULL,
  environment TEXT NOT NULL, year INTEGER NOT NULL, series TEXT NOT NULL, start_number INTEGER NOT NULL, end_number INTEGER NOT NULL,
  reason TEXT NOT NULL, state TEXT NOT NULL, provider_status TEXT NOT NULL, protocol TEXT, provider_request_id TEXT,
  attempts INTEGER NOT NULL DEFAULT 0, error_code TEXT, error_message TEXT, created_by TEXT NOT NULL,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id,document_type,environment,year,series,start_number,end_number)
);
CREATE TABLE IF NOT EXISTS fiscal_provider_event_requests (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, fiscal_document_id TEXT NOT NULL REFERENCES fiscal_documents(id),
  event_type TEXT NOT NULL, payload_json TEXT NOT NULL DEFAULT '{}', reason TEXT NOT NULL, state TEXT NOT NULL,
  provider_status TEXT NOT NULL, protocol TEXT, provider_event_id TEXT, attempts INTEGER NOT NULL DEFAULT 0,
  error_code TEXT, error_message TEXT, created_by TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_fiscal_provider_config_status ON fiscal_provider_configurations(tenant_id,document_type,environment,status);
CREATE INDEX IF NOT EXISTS ix_fiscal_attempt_document ON fiscal_document_attempts(tenant_id,fiscal_document_id,operation,created_at);
CREATE INDEX IF NOT EXISTS ix_fiscal_artifact_document ON fiscal_document_artifacts(tenant_id,fiscal_document_id,artifact_type,created_at);
CREATE INDEX IF NOT EXISTS ix_fiscal_inutilization_status ON fiscal_inutilization_requests(tenant_id,state,created_at);
CREATE INDEX IF NOT EXISTS ix_fiscal_provider_event_status ON fiscal_provider_event_requests(tenant_id,fiscal_document_id,state,created_at);


-- 0041: resiliência de entrega fiscal, rejeições explicáveis e renderer local.
CREATE TABLE IF NOT EXISTS fiscal_document_delivery_policies (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, code TEXT NOT NULL, name TEXT NOT NULL,
  document_type TEXT NOT NULL DEFAULT 'any', provider_code TEXT, environment TEXT NOT NULL DEFAULT 'any',
  valid_from TEXT NOT NULL, valid_until TEXT, priority INTEGER NOT NULL DEFAULT 100,
  max_attempts INTEGER NOT NULL DEFAULT 3, base_delay_seconds INTEGER NOT NULL DEFAULT 30,
  max_delay_seconds INTEGER NOT NULL DEFAULT 1800, backoff_multiplier NUMERIC NOT NULL DEFAULT 2,
  jitter_seconds INTEGER NOT NULL DEFAULT 0, auto_retry INTEGER NOT NULL DEFAULT 1,
  contingency_after_attempts INTEGER, contingency_mode TEXT, notes TEXT,
  state TEXT NOT NULL DEFAULT 'draft', version INTEGER NOT NULL DEFAULT 1, created_by TEXT NOT NULL,
  published_by TEXT, published_at TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id,code,version)
);
CREATE TABLE IF NOT EXISTS fiscal_document_rejections (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, fiscal_document_id TEXT NOT NULL REFERENCES fiscal_documents(id),
  attempt_id TEXT REFERENCES fiscal_document_attempts(id), delivery_policy_id TEXT REFERENCES fiscal_document_delivery_policies(id),
  error_code TEXT, error_message TEXT, category TEXT NOT NULL, retryable INTEGER NOT NULL DEFAULT 0,
  provider_status TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'open', next_retry_at TEXT,
  explanation_json TEXT NOT NULL DEFAULT '{}', resolution TEXT, resolved_at TEXT, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_fiscal_delivery_policy_effective ON fiscal_document_delivery_policies(tenant_id,state,document_type,environment,valid_from,valid_until,priority);
CREATE INDEX IF NOT EXISTS ix_fiscal_rejection_document ON fiscal_document_rejections(tenant_id,fiscal_document_id,state,created_at);

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
  reason TEXT, created_by TEXT NOT NULL, approved_by TEXT, created_at TEXT NOT NULL, finalized_at TEXT,
  started_at TEXT, snapshot_json TEXT NOT NULL DEFAULT '{}', institution_id TEXT, unit_id TEXT,
  version INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS inventory_count_items (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, inventory_count_id TEXT NOT NULL REFERENCES inventory_counts(id),
  product_id TEXT NOT NULL REFERENCES products(id), expected_quantity NUMERIC NOT NULL, counted_quantity NUMERIC NOT NULL,
  difference NUMERIC NOT NULL, movement_id TEXT, lot_id TEXT, notes TEXT, created_at TEXT NOT NULL,
  UNIQUE(inventory_count_id, product_id, lot_id)
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


-- Incremento vertical: catálogo de serviços, compras, lotes, reservas e patrimônio detalhado.
CREATE TABLE IF NOT EXISTS service_catalogs (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, code TEXT NOT NULL, name TEXT NOT NULL, description TEXT,
  valid_from TEXT, valid_until TEXT, state TEXT NOT NULL DEFAULT 'active', institution_id TEXT, unit_id TEXT,
  version INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(tenant_id,code)
);
CREATE TABLE IF NOT EXISTS service_variants (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, service_id TEXT NOT NULL REFERENCES services(id), code TEXT NOT NULL,
  name TEXT NOT NULL, description TEXT, duration_minutes INTEGER, capacity INTEGER, state TEXT NOT NULL DEFAULT 'active',
  metadata_json TEXT NOT NULL DEFAULT '{}', institution_id TEXT, unit_id TEXT, version INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(tenant_id,service_id,code)
);
CREATE TABLE IF NOT EXISTS service_fiscal_profiles (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, service_id TEXT NOT NULL REFERENCES services(id), variant_id TEXT,
  valid_from TEXT NOT NULL, valid_until TEXT, nbs_code TEXT, lc116_code TEXT, municipal_service_code TEXT, cnae_code TEXT,
  iss_rate NUMERIC NOT NULL DEFAULT 0, ibs_rate NUMERIC NOT NULL DEFAULT 0, cbs_rate NUMERIC NOT NULL DEFAULT 0,
  cclass_trib TEXT, fiscal_trigger TEXT NOT NULL DEFAULT 'billing', withholding_json TEXT NOT NULL DEFAULT '{}',
  rules_snapshot_json TEXT NOT NULL DEFAULT '{}', state TEXT NOT NULL DEFAULT 'draft', classification_status TEXT NOT NULL DEFAULT 'incomplete',
  published_at TEXT, published_by TEXT, institution_id TEXT, unit_id TEXT, version INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS service_price_tables (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, service_id TEXT NOT NULL REFERENCES services(id), variant_id TEXT,
  name TEXT NOT NULL, valid_from TEXT NOT NULL, valid_until TEXT, currency TEXT NOT NULL DEFAULT 'BRL',
  amount NUMERIC NOT NULL, billing_frequency TEXT NOT NULL DEFAULT 'one_time', state TEXT NOT NULL DEFAULT 'active',
  institution_id TEXT, unit_id TEXT, version INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS service_billing_rules (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, service_id TEXT NOT NULL REFERENCES services(id), variant_id TEXT,
  code TEXT NOT NULL, name TEXT NOT NULL, billing_trigger TEXT NOT NULL DEFAULT 'competence', due_day INTEGER NOT NULL DEFAULT 10,
  installment_count INTEGER NOT NULL DEFAULT 1, interval_months INTEGER NOT NULL DEFAULT 1,
  recognition_policy TEXT NOT NULL DEFAULT 'competence', fiscal_trigger TEXT NOT NULL DEFAULT 'competence',
  proration_policy TEXT NOT NULL DEFAULT 'none', state TEXT NOT NULL DEFAULT 'active', config_json TEXT NOT NULL DEFAULT '{}',
  institution_id TEXT, unit_id TEXT, version INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id,service_id,code)
);
CREATE TABLE IF NOT EXISTS service_subscriptions (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, subscription_number TEXT NOT NULL, service_id TEXT NOT NULL REFERENCES services(id),
  variant_id TEXT, subscriber_person_id TEXT NOT NULL REFERENCES people(id), enrollment_id TEXT REFERENCES enrollments(id),
  financial_contract_id TEXT REFERENCES financial_contracts(id), billing_rule_id TEXT NOT NULL REFERENCES service_billing_rules(id),
  starts_on TEXT NOT NULL, ends_on TEXT, quantity NUMERIC NOT NULL DEFAULT 1, unit_price NUMERIC NOT NULL,
  discount_amount NUMERIC NOT NULL DEFAULT 0, cycle_amount NUMERIC NOT NULL, next_competence_on TEXT NOT NULL,
  auto_renew INTEGER NOT NULL DEFAULT 0, state TEXT NOT NULL DEFAULT 'draft', suspended_at TEXT, cancelled_at TEXT,
  cancellation_reason TEXT, institution_id TEXT, unit_id TEXT, version INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(tenant_id,subscription_number)
);
CREATE TABLE IF NOT EXISTS service_executions (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, execution_number TEXT NOT NULL, service_order_id TEXT NOT NULL REFERENCES service_orders(id),
  service_order_item_id TEXT NOT NULL REFERENCES service_order_items(id), subscription_id TEXT, scheduled_at TEXT, started_at TEXT,
  completed_at TEXT, quantity NUMERIC NOT NULL, state TEXT NOT NULL DEFAULT 'scheduled', performer_person_id TEXT REFERENCES people(id),
  notes TEXT, evidence_json TEXT NOT NULL DEFAULT '{}', institution_id TEXT, unit_id TEXT, version INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(tenant_id,execution_number)
);
CREATE TABLE IF NOT EXISTS service_competencies (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, subscription_id TEXT NOT NULL REFERENCES service_subscriptions(id),
  competence_key TEXT NOT NULL, period_start TEXT NOT NULL, period_end TEXT NOT NULL, due_date TEXT NOT NULL, amount NUMERIC NOT NULL,
  service_order_id TEXT, charge_id TEXT, state TEXT NOT NULL DEFAULT 'pending', billed_at TEXT,
  institution_id TEXT, unit_id TEXT, version INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id,subscription_id,competence_key)
);
CREATE TABLE IF NOT EXISTS service_fiscal_events (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, event_key TEXT NOT NULL, service_order_id TEXT NOT NULL REFERENCES service_orders(id),
  service_order_item_id TEXT, competence_id TEXT, trigger_type TEXT NOT NULL, document_type TEXT NOT NULL DEFAULT 'nfse',
  provider_code TEXT, fiscal_document_id TEXT REFERENCES fiscal_documents(id), fiscal_assembly_id TEXT REFERENCES fiscal_document_assemblies(id),
  state TEXT NOT NULL DEFAULT 'not_configured', payload_snapshot_json TEXT NOT NULL DEFAULT '{}',
  requested_at TEXT NOT NULL, completed_at TEXT, failure_code TEXT, failure_message TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id,event_key)
);
CREATE INDEX IF NOT EXISTS ix_service_fiscal_event_document ON service_fiscal_events(tenant_id,fiscal_document_id,state,updated_at);
CREATE TABLE IF NOT EXISTS charges (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, charge_number TEXT NOT NULL, financial_contract_id TEXT REFERENCES financial_contracts(id),
  enrollment_id TEXT REFERENCES enrollments(id), responsible_person_id TEXT REFERENCES people(id), origin_type TEXT NOT NULL, origin_id TEXT NOT NULL,
  currency TEXT NOT NULL DEFAULT 'BRL', total_amount NUMERIC NOT NULL, paid_amount NUMERIC NOT NULL DEFAULT 0,
  refunded_amount NUMERIC NOT NULL DEFAULT 0, outstanding_amount NUMERIC NOT NULL, due_date TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'open', generated_at TEXT NOT NULL, cancelled_at TEXT, cancellation_reason TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(tenant_id,charge_number), UNIQUE(tenant_id,origin_type,origin_id)
);
CREATE TABLE IF NOT EXISTS charge_items (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, charge_id TEXT NOT NULL REFERENCES charges(id), description TEXT NOT NULL,
  quantity NUMERIC NOT NULL DEFAULT 1, unit_amount NUMERIC NOT NULL, discount_amount NUMERIC NOT NULL DEFAULT 0,
  total_amount NUMERIC NOT NULL, accounting_code TEXT, metadata_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS accounts_receivable (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, receivable_number TEXT NOT NULL, installment_id TEXT REFERENCES installments(id),
  charge_id TEXT REFERENCES charges(id), responsible_person_id TEXT REFERENCES people(id), cost_center_id TEXT, amount NUMERIC NOT NULL,
  paid_amount NUMERIC NOT NULL DEFAULT 0, refunded_amount NUMERIC NOT NULL DEFAULT 0, outstanding_amount NUMERIC NOT NULL,
  due_date TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'open', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id,receivable_number)
);

CREATE TABLE IF NOT EXISTS product_variants (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, product_id TEXT NOT NULL REFERENCES products(id), sku TEXT NOT NULL, name TEXT NOT NULL,
  attributes_json TEXT NOT NULL DEFAULT '{}', sale_price NUMERIC, cost_price NUMERIC, state TEXT NOT NULL DEFAULT 'active',
  institution_id TEXT, unit_id TEXT, version INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id,sku)
);
CREATE TABLE IF NOT EXISTS product_barcodes (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, product_id TEXT NOT NULL REFERENCES products(id), variant_id TEXT, barcode TEXT NOT NULL,
  barcode_type TEXT NOT NULL DEFAULT 'ean13', is_primary INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
  UNIQUE(tenant_id,barcode)
);
CREATE TABLE IF NOT EXISTS supplier_contacts (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, supplier_id TEXT NOT NULL REFERENCES suppliers(id), name TEXT NOT NULL, email TEXT,
  phone TEXT, role TEXT, is_primary INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS purchase_requisitions (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, requisition_number TEXT NOT NULL, requester_user_id TEXT NOT NULL, department_id TEXT,
  cost_center_id TEXT, needed_by TEXT, justification TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'draft', submitted_at TEXT, submitted_by TEXT,
  approved_at TEXT, approved_by TEXT, rejected_at TEXT, rejected_by TEXT, rejection_reason TEXT, cancelled_at TEXT, cancelled_by TEXT,
  cancellation_reason TEXT, institution_id TEXT, unit_id TEXT, version INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id,requisition_number)
);
CREATE TABLE IF NOT EXISTS purchase_requisition_items (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, requisition_id TEXT NOT NULL REFERENCES purchase_requisitions(id), product_id TEXT NOT NULL REFERENCES products(id),
  quantity NUMERIC NOT NULL, approved_quantity NUMERIC NOT NULL DEFAULT 0, estimated_unit_price NUMERIC NOT NULL DEFAULT 0,
  notes TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS requests_for_quotation (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, quotation_number TEXT NOT NULL, requisition_id TEXT REFERENCES purchase_requisitions(id),
  response_deadline TEXT, currency TEXT NOT NULL DEFAULT 'BRL', state TEXT NOT NULL DEFAULT 'open', selected_supplier_id TEXT REFERENCES suppliers(id),
  selection_reason TEXT, awarded_at TEXT, awarded_by TEXT, institution_id TEXT, unit_id TEXT, version INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(tenant_id,quotation_number)
);
CREATE TABLE IF NOT EXISTS quotation_items (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, quotation_id TEXT NOT NULL REFERENCES requests_for_quotation(id),
  product_id TEXT NOT NULL REFERENCES products(id), quantity NUMERIC NOT NULL, specifications_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS quotation_suppliers (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, quotation_id TEXT NOT NULL REFERENCES requests_for_quotation(id),
  supplier_id TEXT NOT NULL REFERENCES suppliers(id), state TEXT NOT NULL DEFAULT 'invited', invited_at TEXT NOT NULL, submitted_at TEXT,
  delivery_days INTEGER, payment_terms_json TEXT NOT NULL DEFAULT '{}', notes TEXT, total_amount NUMERIC NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(tenant_id,quotation_id,supplier_id)
);
CREATE TABLE IF NOT EXISTS quotation_supplier_items (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, quotation_supplier_id TEXT NOT NULL REFERENCES quotation_suppliers(id),
  quotation_item_id TEXT NOT NULL REFERENCES quotation_items(id), unit_price NUMERIC NOT NULL, quantity_available NUMERIC NOT NULL,
  brand TEXT, notes TEXT, created_at TEXT NOT NULL, UNIQUE(tenant_id,quotation_supplier_id,quotation_item_id)
);
CREATE TABLE IF NOT EXISTS goods_receipts (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, receipt_number TEXT NOT NULL, purchase_order_id TEXT NOT NULL REFERENCES purchase_orders(id),
  supplier_id TEXT NOT NULL REFERENCES suppliers(id), warehouse_id TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'confirmed',
  received_at TEXT NOT NULL, received_by TEXT NOT NULL, supplier_document_number TEXT, supplier_document_key TEXT,
  total_amount NUMERIC NOT NULL DEFAULT 0, notes TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id,receipt_number)
);
CREATE TABLE IF NOT EXISTS goods_receipt_items (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, goods_receipt_id TEXT NOT NULL REFERENCES goods_receipts(id),
  purchase_order_item_id TEXT NOT NULL REFERENCES purchase_order_items(id), product_id TEXT NOT NULL REFERENCES products(id),
  quantity NUMERIC NOT NULL, unit_cost NUMERIC NOT NULL, lot_id TEXT, stock_movement_id TEXT, expires_on TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS inventory_lots (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, product_id TEXT NOT NULL REFERENCES products(id), warehouse_id TEXT NOT NULL,
  lot_number TEXT NOT NULL, manufactured_on TEXT, expires_on TEXT, quantity NUMERIC NOT NULL DEFAULT 0, reserved_quantity NUMERIC NOT NULL DEFAULT 0,
  unit_cost NUMERIC NOT NULL DEFAULT 0, state TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id,product_id,warehouse_id,lot_number)
);
CREATE TABLE IF NOT EXISTS purchase_returns (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, return_number TEXT NOT NULL, purchase_order_id TEXT NOT NULL REFERENCES purchase_orders(id),
  supplier_id TEXT NOT NULL REFERENCES suppliers(id), warehouse_id TEXT NOT NULL, reason TEXT NOT NULL, total_amount NUMERIC NOT NULL DEFAULT 0,
  state TEXT NOT NULL DEFAULT 'confirmed', returned_at TEXT NOT NULL, returned_by TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id,return_number)
);
CREATE TABLE IF NOT EXISTS purchase_return_items (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, purchase_return_id TEXT NOT NULL REFERENCES purchase_returns(id),
  purchase_order_item_id TEXT NOT NULL REFERENCES purchase_order_items(id), product_id TEXT NOT NULL REFERENCES products(id),
  lot_id TEXT, quantity NUMERIC NOT NULL, unit_cost NUMERIC NOT NULL, stock_movement_id TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS inventory_reservations (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, product_id TEXT NOT NULL REFERENCES products(id), warehouse_id TEXT NOT NULL, lot_id TEXT,
  source_type TEXT NOT NULL, source_id TEXT NOT NULL, quantity NUMERIC NOT NULL, consumed_quantity NUMERIC NOT NULL DEFAULT 0,
  state TEXT NOT NULL DEFAULT 'active', expires_at TEXT, released_at TEXT, consumed_at TEXT, institution_id TEXT, unit_id TEXT,
  version INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id,source_type,source_id,product_id,warehouse_id,lot_id)
);

CREATE TABLE IF NOT EXISTS inventory_reorder_policies (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, product_id TEXT NOT NULL REFERENCES products(id),
  warehouse_id TEXT NOT NULL DEFAULT 'default', minimum_quantity NUMERIC NOT NULL, target_quantity NUMERIC NOT NULL,
  lead_time_days INTEGER NOT NULL DEFAULT 0, preferred_supplier_id TEXT REFERENCES suppliers(id),
  state TEXT NOT NULL DEFAULT 'active', institution_id TEXT, unit_id TEXT, version INTEGER NOT NULL DEFAULT 1,
  created_by TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id,product_id,warehouse_id)
);
CREATE TABLE IF NOT EXISTS purchase_suggestions (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, policy_id TEXT NOT NULL REFERENCES inventory_reorder_policies(id),
  product_id TEXT NOT NULL REFERENCES products(id), warehouse_id TEXT NOT NULL,
  preferred_supplier_id TEXT REFERENCES suppliers(id), physical_quantity NUMERIC NOT NULL DEFAULT 0,
  reserved_quantity NUMERIC NOT NULL DEFAULT 0, available_quantity NUMERIC NOT NULL DEFAULT 0,
  open_purchase_quantity NUMERIC NOT NULL DEFAULT 0, projected_quantity NUMERIC NOT NULL DEFAULT 0,
  minimum_quantity NUMERIC NOT NULL, target_quantity NUMERIC NOT NULL, suggested_quantity NUMERIC NOT NULL,
  estimated_unit_cost NUMERIC NOT NULL DEFAULT 0, estimated_total NUMERIC NOT NULL DEFAULT 0,
  reason TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'open', requisition_id TEXT REFERENCES purchase_requisitions(id),
  generated_at TEXT NOT NULL, generated_by TEXT NOT NULL, converted_at TEXT, converted_by TEXT,
  closed_at TEXT, closed_by TEXT, closure_reason TEXT, version INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_inventory_reorder_policies_state
  ON inventory_reorder_policies(tenant_id,state,warehouse_id,product_id);
CREATE INDEX IF NOT EXISTS ix_purchase_suggestions_state
  ON purchase_suggestions(tenant_id,state,generated_at);
CREATE UNIQUE INDEX IF NOT EXISTS uq_purchase_suggestions_open_policy
  ON purchase_suggestions(tenant_id,policy_id) WHERE state='open';

CREATE TABLE IF NOT EXISTS asset_locations (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, code TEXT NOT NULL, name TEXT NOT NULL, parent_id TEXT REFERENCES asset_locations(id),
  state TEXT NOT NULL DEFAULT 'active', institution_id TEXT, unit_id TEXT, version INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(tenant_id,code)
);
CREATE TABLE IF NOT EXISTS asset_movements (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, asset_id TEXT NOT NULL REFERENCES assets(id), movement_type TEXT NOT NULL,
  from_location_id TEXT, to_location_id TEXT, from_responsible_person_id TEXT, to_responsible_person_id TEXT,
  reason TEXT NOT NULL, occurred_at TEXT NOT NULL, occurred_by TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS asset_maintenances (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, asset_id TEXT NOT NULL REFERENCES assets(id), maintenance_number TEXT NOT NULL,
  maintenance_type TEXT NOT NULL, scheduled_on TEXT, supplier_id TEXT REFERENCES suppliers(id), estimated_cost NUMERIC NOT NULL DEFAULT 0,
  actual_cost NUMERIC, description TEXT NOT NULL, result_notes TEXT, state TEXT NOT NULL DEFAULT 'scheduled', started_at TEXT,
  completed_at TEXT, created_by TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id,maintenance_number)
);
CREATE TABLE IF NOT EXISTS asset_loans (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, asset_id TEXT NOT NULL REFERENCES assets(id), loan_number TEXT NOT NULL,
  borrower_person_id TEXT NOT NULL REFERENCES people(id), loaned_at TEXT NOT NULL, expected_return_at TEXT, returned_at TEXT,
  condition_out TEXT, condition_in TEXT, state TEXT NOT NULL DEFAULT 'active', created_by TEXT NOT NULL, returned_by TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(tenant_id,loan_number)
);
CREATE TABLE IF NOT EXISTS asset_depreciations (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, asset_id TEXT NOT NULL REFERENCES assets(id), competence TEXT NOT NULL,
  opening_book_value NUMERIC NOT NULL, depreciation_amount NUMERIC NOT NULL, accumulated_depreciation NUMERIC NOT NULL,
  closing_book_value NUMERIC NOT NULL, method TEXT NOT NULL DEFAULT 'linear', calculated_at TEXT NOT NULL, calculated_by TEXT NOT NULL,
  created_at TEXT NOT NULL, UNIQUE(tenant_id,asset_id,competence)
);

CREATE INDEX IF NOT EXISTS ix_service_prices_validity ON service_price_tables(tenant_id,service_id,variant_id,valid_from,valid_until,state);
CREATE INDEX IF NOT EXISTS ix_service_subscriptions_status ON service_subscriptions(tenant_id,state,next_competence_on);
CREATE INDEX IF NOT EXISTS ix_service_orders_status ON service_orders(tenant_id,state,created_at);
CREATE INDEX IF NOT EXISTS ix_requisitions_status ON purchase_requisitions(tenant_id,state,created_at);
CREATE INDEX IF NOT EXISTS ix_quotations_status ON requests_for_quotation(tenant_id,state,created_at);
CREATE INDEX IF NOT EXISTS ix_inventory_lots_expiry ON inventory_lots(tenant_id,warehouse_id,expires_on,state);
CREATE INDEX IF NOT EXISTS ix_inventory_reservations_product ON inventory_reservations(tenant_id,product_id,warehouse_id,state);
CREATE INDEX IF NOT EXISTS ix_asset_movements_asset ON asset_movements(tenant_id,asset_id,occurred_at);

CREATE TABLE IF NOT EXISTS fiscal_catalogs (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, kind TEXT NOT NULL, name TEXT NOT NULL, description TEXT,
  normalization TEXT NOT NULL DEFAULT 'upper_alnum', code_pattern TEXT, metadata_json TEXT NOT NULL DEFAULT '{}',
  state TEXT NOT NULL DEFAULT 'active', active_version_id TEXT, latest_version_number INTEGER NOT NULL DEFAULT 0,
  version INTEGER NOT NULL DEFAULT 1, created_by TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id,kind)
);
CREATE TABLE IF NOT EXISTS fiscal_catalog_versions (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, fiscal_catalog_id TEXT NOT NULL REFERENCES fiscal_catalogs(id),
  version_number INTEGER NOT NULL, version_label TEXT NOT NULL, valid_from TEXT NOT NULL, valid_until TEXT,
  source_name TEXT NOT NULL, source_reference TEXT, source_sha256 TEXT NOT NULL, schema_version TEXT, notes TEXT,
  state TEXT NOT NULL DEFAULT 'draft', published_at TEXT, published_by TEXT, entries_count INTEGER NOT NULL DEFAULT 0,
  version INTEGER NOT NULL DEFAULT 1, created_by TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id,fiscal_catalog_id,version_number)
);
CREATE TABLE IF NOT EXISTS fiscal_catalog_entries (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, fiscal_catalog_version_id TEXT NOT NULL REFERENCES fiscal_catalog_versions(id),
  code TEXT NOT NULL, description TEXT NOT NULL, parent_code TEXT, metadata_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL,
  UNIQUE(tenant_id,fiscal_catalog_version_id,code)
);
CREATE TABLE IF NOT EXISTS fiscal_classification_rules (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, fiscal_context_id TEXT NOT NULL REFERENCES fiscal_contexts(id),
  establishment_code TEXT, item_kind TEXT NOT NULL, item_id TEXT, operation_type TEXT NOT NULL,
  valid_from TEXT NOT NULL, valid_until TEXT, priority INTEGER NOT NULL DEFAULT 100,
  ncm TEXT, nbs TEXT, lc116 TEXT, cfop TEXT, cest TEXT, cst TEXT, csosn TEXT, cst_ibs_cbs TEXT,
  cclasstrib TEXT, cbenef TEXT, municipal_code TEXT, cnae TEXT, tax_configuration_json TEXT NOT NULL DEFAULT '{}',
  notes TEXT, state TEXT NOT NULL DEFAULT 'draft', published_at TEXT, published_by TEXT,
  version INTEGER NOT NULL DEFAULT 1, created_by TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_fiscal_catalog_versions_effective
  ON fiscal_catalog_versions(tenant_id,fiscal_catalog_id,state,valid_from,valid_until);
CREATE INDEX IF NOT EXISTS ix_fiscal_catalog_entries_code
  ON fiscal_catalog_entries(tenant_id,fiscal_catalog_version_id,code);
CREATE INDEX IF NOT EXISTS ix_fiscal_classification_rules_resolution
  ON fiscal_classification_rules(tenant_id,fiscal_context_id,item_kind,operation_type,state,valid_from,valid_until,priority);

CREATE TABLE IF NOT EXISTS fiscal_tax_rule_sets (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, fiscal_context_id TEXT NOT NULL REFERENCES fiscal_contexts(id),
  code TEXT NOT NULL, name TEXT NOT NULL, description TEXT, establishment_code TEXT,
  operation_type TEXT NOT NULL DEFAULT 'sale', item_kind TEXT NOT NULL DEFAULT 'any', tax_regime TEXT NOT NULL DEFAULT 'any', rtc_mode TEXT NOT NULL DEFAULT 'any',
  priority INTEGER NOT NULL DEFAULT 100, state TEXT NOT NULL DEFAULT 'active', active_version_id TEXT,
  latest_version_number INTEGER NOT NULL DEFAULT 0, version INTEGER NOT NULL DEFAULT 1, created_by TEXT NOT NULL,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(tenant_id,code)
);
CREATE TABLE IF NOT EXISTS fiscal_tax_rule_versions (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, fiscal_tax_rule_set_id TEXT NOT NULL REFERENCES fiscal_tax_rule_sets(id),
  version_number INTEGER NOT NULL, version_label TEXT NOT NULL, valid_from TEXT NOT NULL, valid_until TEXT,
  source_name TEXT NOT NULL, source_reference TEXT, source_sha256 TEXT NOT NULL, legal_basis_json TEXT NOT NULL DEFAULT '[]',
  components_json TEXT NOT NULL DEFAULT '[]', notes TEXT, state TEXT NOT NULL DEFAULT 'draft', published_at TEXT, published_by TEXT,
  version INTEGER NOT NULL DEFAULT 1, created_by TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id,fiscal_tax_rule_set_id,version_number)
);
CREATE TABLE IF NOT EXISTS fiscal_tax_calculations (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, fiscal_context_id TEXT NOT NULL REFERENCES fiscal_contexts(id),
  fiscal_context_version_id TEXT NOT NULL REFERENCES fiscal_context_versions(id), fiscal_tax_rule_set_id TEXT NOT NULL REFERENCES fiscal_tax_rule_sets(id),
  fiscal_tax_rule_version_id TEXT NOT NULL REFERENCES fiscal_tax_rule_versions(id), item_kind TEXT NOT NULL, item_id TEXT,
  operation_type TEXT NOT NULL, occurred_on TEXT NOT NULL, input_json TEXT NOT NULL, result_json TEXT NOT NULL,
  snapshot_sha256 TEXT NOT NULL, tax_total NUMERIC NOT NULL DEFAULT 0, has_divergence INTEGER NOT NULL DEFAULT 0,
  created_by TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_fiscal_tax_rule_sets_resolution ON fiscal_tax_rule_sets(tenant_id,fiscal_context_id,state,establishment_code,operation_type,item_kind,tax_regime,rtc_mode,priority);
CREATE INDEX IF NOT EXISTS ix_fiscal_tax_rule_versions_effective ON fiscal_tax_rule_versions(tenant_id,fiscal_tax_rule_set_id,state,valid_from,valid_until);
CREATE INDEX IF NOT EXISTS ix_fiscal_tax_calculations_lookup ON fiscal_tax_calculations(tenant_id,fiscal_context_id,occurred_on,operation_type,item_kind);

-- Estratégias tributárias e cronograma RTC versionado.
CREATE TABLE IF NOT EXISTS fiscal_legal_source_artifacts (id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, kind TEXT NOT NULL, title TEXT NOT NULL, version_label TEXT NOT NULL, valid_from TEXT NOT NULL, valid_until TEXT, source_reference TEXT, source_sha256 TEXT NOT NULL, metadata_json TEXT NOT NULL DEFAULT '{}', state TEXT NOT NULL DEFAULT 'published', created_by TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS fiscal_strategy_rules (id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, fiscal_context_id TEXT NOT NULL REFERENCES fiscal_contexts(id), establishment_code TEXT, strategy_type TEXT NOT NULL, operation_type TEXT NOT NULL, tax_regime TEXT NOT NULL, rtc_mode TEXT NOT NULL, origin_uf TEXT, destination_uf TEXT, valid_from TEXT NOT NULL, valid_until TEXT, priority INTEGER NOT NULL DEFAULT 100, parameters_json TEXT NOT NULL DEFAULT '{}', legal_source_id TEXT REFERENCES fiscal_legal_source_artifacts(id), state TEXT NOT NULL DEFAULT 'published', version INTEGER NOT NULL DEFAULT 1, created_by TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_fiscal_strategy_resolution ON fiscal_strategy_rules(tenant_id,fiscal_context_id,state,valid_from,valid_until,priority);
CREATE TABLE IF NOT EXISTS fiscal_rtc_schedules (id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, fiscal_context_id TEXT NOT NULL REFERENCES fiscal_contexts(id), establishment_code TEXT, tax_regime TEXT NOT NULL, mode TEXT NOT NULL, valid_from TEXT NOT NULL, valid_until TEXT, legal_source_id TEXT REFERENCES fiscal_legal_source_artifacts(id), notes TEXT, state TEXT NOT NULL DEFAULT 'published', version INTEGER NOT NULL DEFAULT 1, created_by TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_fiscal_rtc_resolution ON fiscal_rtc_schedules(tenant_id,fiscal_context_id,state,valid_from,valid_until);
CREATE TABLE IF NOT EXISTS ibpt_quarantine_items (id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, sync_run_id TEXT NOT NULL, uf TEXT NOT NULL, source_url TEXT, sha256 TEXT NOT NULL, storage_key TEXT NOT NULL, bytes_count INTEGER NOT NULL, reason_code TEXT NOT NULL, reason_message TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'open', created_at TEXT NOT NULL, resolved_at TEXT, resolved_by TEXT, UNIQUE(tenant_id,sync_run_id,sha256));
CREATE INDEX IF NOT EXISTS ix_ibpt_quarantine_open ON ibpt_quarantine_items(tenant_id,state,uf,created_at);


-- 0037 fiscal catalog governance/imports (SQLite local/test profile)
CREATE TABLE IF NOT EXISTS fiscal_catalog_source_profiles (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, fiscal_catalog_id TEXT NOT NULL, provider_type TEXT NOT NULL,
  provider_key TEXT NOT NULL, provider_version TEXT NOT NULL, import_format TEXT NOT NULL, source_reference TEXT,
  encoding TEXT NOT NULL DEFAULT 'utf-8', delimiter TEXT NOT NULL DEFAULT ';', max_age_days INTEGER NOT NULL DEFAULT 90,
  mapping_json TEXT NOT NULL DEFAULT '{}', schema_json TEXT NOT NULL DEFAULT '{}', state TEXT NOT NULL DEFAULT 'ready',
  last_import_at TEXT, last_success_at TEXT, last_error TEXT, version INTEGER NOT NULL DEFAULT 1, notes TEXT,
  created_by TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id,fiscal_catalog_id,provider_key,provider_version)
);
CREATE INDEX IF NOT EXISTS ix_fiscal_catalog_sources_catalog ON fiscal_catalog_source_profiles(tenant_id,fiscal_catalog_id,state,provider_key);

CREATE TABLE IF NOT EXISTS fiscal_catalog_import_runs (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, fiscal_catalog_id TEXT NOT NULL, source_profile_id TEXT NOT NULL,
  provider_key TEXT NOT NULL, provider_version TEXT NOT NULL, import_format TEXT NOT NULL, original_filename TEXT NOT NULL,
  source_sha256 TEXT NOT NULL, storage_key TEXT NOT NULL, bytes_count INTEGER NOT NULL, state TEXT NOT NULL,
  version_label TEXT NOT NULL, valid_from TEXT NOT NULL, valid_until TEXT, schema_version TEXT, entries_count INTEGER NOT NULL DEFAULT 0,
  diff_json TEXT NOT NULL DEFAULT '{}', catalog_version_id TEXT, error_code TEXT, error_detail TEXT, idempotency_key TEXT,
  requested_by TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, completed_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_fiscal_catalog_import_runs_catalog ON fiscal_catalog_import_runs(tenant_id,fiscal_catalog_id,state,created_at);

CREATE TABLE IF NOT EXISTS fiscal_catalog_quarantine (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, import_run_id TEXT NOT NULL, source_profile_id TEXT NOT NULL,
  fiscal_catalog_id TEXT NOT NULL, reason_code TEXT NOT NULL, reason_detail TEXT NOT NULL, storage_key TEXT NOT NULL,
  source_sha256 TEXT NOT NULL, bytes_count INTEGER NOT NULL, state TEXT NOT NULL DEFAULT 'open', created_at TEXT NOT NULL,
  resolved_at TEXT, resolved_by TEXT, resolution_reason TEXT, UNIQUE(tenant_id,import_run_id,source_sha256)
);
CREATE INDEX IF NOT EXISTS ix_fiscal_catalog_quarantine_open ON fiscal_catalog_quarantine(tenant_id,state,fiscal_catalog_id,created_at);

-- 0039 fiscal document routing and assembly ---------------------------------
CREATE TABLE IF NOT EXISTS fiscal_document_schema_versions (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, document_type TEXT NOT NULL, schema_code TEXT NOT NULL,
  version_label TEXT NOT NULL, valid_from TEXT NOT NULL, valid_until TEXT, root_element TEXT NOT NULL,
  namespace_uri TEXT, source_reference TEXT, xsd_storage_key TEXT NOT NULL, xsd_sha256 TEXT NOT NULL,
  metadata_json TEXT NOT NULL DEFAULT '{}', state TEXT NOT NULL DEFAULT 'draft', version INTEGER NOT NULL DEFAULT 1,
  created_by TEXT NOT NULL, published_by TEXT, published_at TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id, schema_code, version_label)
);
CREATE INDEX IF NOT EXISTS ix_fiscal_document_schema_effective ON fiscal_document_schema_versions(tenant_id,document_type,state,valid_from,valid_until);
CREATE TABLE IF NOT EXISTS fiscal_document_routing_policies (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, fiscal_context_id TEXT NOT NULL REFERENCES fiscal_contexts(id),
  code TEXT NOT NULL, name TEXT NOT NULL, operation_type TEXT NOT NULL, recipient_scope TEXT NOT NULL DEFAULT 'any',
  channel_scope TEXT NOT NULL DEFAULT 'any', product_document_type TEXT, service_document_type TEXT NOT NULL DEFAULT 'NFS-e',
  trigger_types_json TEXT NOT NULL DEFAULT '[]', valid_from TEXT NOT NULL, valid_until TEXT, priority INTEGER NOT NULL DEFAULT 100,
  settings_json TEXT NOT NULL DEFAULT '{}', state TEXT NOT NULL DEFAULT 'draft', version INTEGER NOT NULL DEFAULT 1,
  created_by TEXT NOT NULL, published_by TEXT, published_at TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_fiscal_routing_effective ON fiscal_document_routing_policies(tenant_id,fiscal_context_id,state,operation_type,valid_from,valid_until,priority);
CREATE TABLE IF NOT EXISTS fiscal_document_assemblies (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, source_type TEXT NOT NULL, source_id TEXT NOT NULL,
  fiscal_context_id TEXT NOT NULL REFERENCES fiscal_contexts(id), fiscal_context_version_id TEXT NOT NULL REFERENCES fiscal_context_versions(id),
  routing_policy_id TEXT REFERENCES fiscal_document_routing_policies(id), fiscal_profile_id TEXT NOT NULL REFERENCES fiscal_profiles(id),
  occurred_on TEXT NOT NULL, operation_type TEXT NOT NULL, recipient_scope TEXT NOT NULL, channel TEXT NOT NULL, trigger_type TEXT NOT NULL,
  state TEXT NOT NULL, input_snapshot_json TEXT NOT NULL, input_sha256 TEXT NOT NULL, routing_decision_json TEXT NOT NULL,
  output_snapshot_json TEXT NOT NULL DEFAULT '{}', output_sha256 TEXT, created_by TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_fiscal_assembly_source ON fiscal_document_assemblies(tenant_id,source_type,source_id,created_at);
CREATE TABLE IF NOT EXISTS fiscal_document_builds (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, assembly_id TEXT NOT NULL REFERENCES fiscal_document_assemblies(id),
  document_type TEXT NOT NULL, relationship TEXT NOT NULL, schema_version_id TEXT REFERENCES fiscal_document_schema_versions(id),
  payload_json TEXT NOT NULL, xml_storage_key TEXT, xml_sha256 TEXT, validation_state TEXT NOT NULL,
  validation_errors_json TEXT NOT NULL DEFAULT '[]', total_amount NUMERIC NOT NULL, item_count INTEGER NOT NULL,
  fiscal_document_id TEXT REFERENCES fiscal_documents(id), created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_fiscal_build_assembly ON fiscal_document_builds(tenant_id,assembly_id,document_type);
CREATE TABLE IF NOT EXISTS fiscal_document_links (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, assembly_id TEXT NOT NULL REFERENCES fiscal_document_assemblies(id),
  build_id TEXT NOT NULL REFERENCES fiscal_document_builds(id), fiscal_document_id TEXT NOT NULL REFERENCES fiscal_documents(id),
  source_type TEXT NOT NULL, source_id TEXT NOT NULL, relationship TEXT NOT NULL, created_at TEXT NOT NULL,
  UNIQUE(tenant_id, build_id, fiscal_document_id)
);
CREATE INDEX IF NOT EXISTS ix_fiscal_document_links_source ON fiscal_document_links(tenant_id,source_type,source_id);
CREATE TABLE IF NOT EXISTS fiscal_emission_trigger_runs (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, event_type TEXT NOT NULL, aggregate_id TEXT NOT NULL,
  source_type TEXT, source_id TEXT, trigger_type TEXT NOT NULL, routing_policy_id TEXT REFERENCES fiscal_document_routing_policies(id),
  state TEXT NOT NULL, payload_json TEXT NOT NULL DEFAULT '{}', error_detail TEXT, assembly_id TEXT REFERENCES fiscal_document_assemblies(id),
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(tenant_id,event_type,aggregate_id)
);
CREATE INDEX IF NOT EXISTS ix_fiscal_trigger_runs_state ON fiscal_emission_trigger_runs(tenant_id,state,created_at);
CREATE TABLE IF NOT EXISTS fiscal_document_financial_links (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, fiscal_document_id TEXT NOT NULL REFERENCES fiscal_documents(id),
  source_type TEXT NOT NULL, source_id TEXT NOT NULL, financial_contract_id TEXT, charge_id TEXT, payment_id TEXT,
  adjustment_state TEXT NOT NULL DEFAULT 'linked', adjustment_ledger_entry_id TEXT REFERENCES ledger_entries(id),
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(tenant_id,fiscal_document_id,source_type,source_id)
);
CREATE INDEX IF NOT EXISTS ix_fiscal_financial_links_charge ON fiscal_document_financial_links(tenant_id,charge_id,adjustment_state);


-- 0040 IBPT por tenant e transparência tributária ---------------------------
CREATE TABLE IF NOT EXISTS fiscal_ibpt_provider_profiles (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, provider_code TEXT NOT NULL, mode TEXT NOT NULL,
  valid_from TEXT NOT NULL, valid_until TEXT, sync_enabled INTEGER NOT NULL DEFAULT 0,
  fallback_enabled INTEGER NOT NULL DEFAULT 1, fallback_max_age_days INTEGER NOT NULL DEFAULT 90,
  stale_after_days INTEGER NOT NULL DEFAULT 120, base_url TEXT NOT NULL, uf_path TEXT NOT NULL,
  notes TEXT, state TEXT NOT NULL DEFAULT 'draft', version INTEGER NOT NULL DEFAULT 1,
  created_by TEXT NOT NULL, published_by TEXT, published_at TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  CHECK(mode IN ('disabled','local_snapshot','remote_sync')),
  CHECK(state IN ('draft','published','superseded','archived')),
  CHECK(valid_until IS NULL OR valid_until>=valid_from)
);
CREATE INDEX IF NOT EXISTS ix_fiscal_ibpt_profile_effective
  ON fiscal_ibpt_provider_profiles(tenant_id,state,valid_from,valid_until,version);

CREATE TABLE IF NOT EXISTS fiscal_document_tax_transparency (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, build_id TEXT NOT NULL REFERENCES fiscal_document_builds(id),
  fiscal_document_id TEXT REFERENCES fiscal_documents(id), real_taxes_json TEXT NOT NULL DEFAULT '{}',
  approximate_ibpt_json TEXT NOT NULL DEFAULT '{}', vtottrib NUMERIC NOT NULL DEFAULT 0,
  ibpt_provider_profile_id TEXT REFERENCES fiscal_ibpt_provider_profiles(id), created_at TEXT NOT NULL,
  UNIQUE(tenant_id,build_id)
);
CREATE INDEX IF NOT EXISTS ix_fiscal_tax_transparency_document
  ON fiscal_document_tax_transparency(tenant_id,fiscal_document_id,created_at);
