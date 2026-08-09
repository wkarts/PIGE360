# Catálogo de domínios

| Recurso | Rota | Estado inicial | Papéis principais | Evento |
|---|---|---|---|---|
| `people` | `/api/v1/people` | `active` | tenant_owner, institution_director, secretary, hr_manager | `Person*` |
| `students` | `/api/v1/students` | `active` | tenant_owner, secretary, academic_coordinator | `Student*` |
| `guardians` | `/api/v1/guardians` | `active` | tenant_owner, secretary | `Guardian*` |
| `employees` | `/api/v1/employees` | `draft` | tenant_owner, hr_manager, personnel_operator | `Employee*` |
| `admissions` | `/api/v1/admissions/candidates` | `lead` | tenant_owner, secretary | `Admission*` |
| `enrollments` | `/api/v1/enrollments` | `draft` | tenant_owner, secretary, institution_director | `Enrollment*` |
| `programs` | `/api/v1/academic/programs` | `draft` | tenant_owner, academic_coordinator | `AcademicProgram*` |
| `curricula` | `/api/v1/academic/curricula` | `draft` | tenant_owner, academic_coordinator | `Curriculum*` |
| `class_groups` | `/api/v1/academic/class-groups` | `draft` | tenant_owner, academic_coordinator, secretary | `ClassGroup*` |
| `evaluations` | `/api/v1/pedagogy/evaluations` | `draft` | teacher, academic_coordinator | `Evaluation*` |
| `grades` | `/api/v1/pedagogy/grades` | `draft` | teacher, academic_coordinator | `Grade*` |
| `financial_contracts` | `/api/v1/finance/contracts` | `draft` | tenant_owner, finance_manager, finance_operator | `FinancialContract*` |
| `charges` | `/api/v1/finance/charges` | `draft` | finance_manager, finance_operator | `Charge*` |
| `payments` | `/api/v1/finance/payments` | `pending` | finance_manager, finance_operator | `Payment*` |
| `bank_accounts` | `/api/v1/banking/accounts` | `active` | finance_manager | `BankAccount*` |
| `reconciliations` | `/api/v1/banking/reconciliations` | `draft` | finance_manager, finance_operator | `Reconciliation*` |
| `services` | `/api/v1/services` | `draft` | tenant_owner, finance_manager | `Service*` |
| `service_orders` | `/api/v1/services/orders` | `draft` | finance_manager, finance_operator | `ServiceOrder*` |
| `sales` | `/api/v1/sales` | `draft` | sales_manager, pos_operator, finance_manager | `Sale*` |
| `pos_sessions` | `/api/v1/pos/sessions` | `closed` | canteen_manager, pos_operator | `PosSession*` |
| `canteen_products` | `/api/v1/canteen/products` | `draft` | canteen_manager, inventory_manager | `CanteenProduct*` |
| `inventory_items` | `/api/v1/inventory/items` | `active` | inventory_manager | `InventoryItem*` |
| `purchase_orders` | `/api/v1/procurement/orders` | `draft` | inventory_manager, finance_manager | `PurchaseOrder*` |
| `assets` | `/api/v1/assets` | `active` | inventory_manager | `Asset*` |
| `fiscal_documents` | `/api/v1/fiscal/documents` | `draft` | fiscal_manager | `FiscalDocument*` |
| `tax_rules` | `/api/v1/fiscal/tax-rules` | `draft` | fiscal_manager | `TaxRule*` |
| `hr_candidates` | `/api/v1/hr/candidates` | `applied` | hr_manager | `HrCandidate*` |
| `payroll_runs` | `/api/v1/payroll/runs` | `draft` | payroll_operator, personnel_operator | `PayrollRun*` |
| `timekeeping_records` | `/api/v1/timekeeping/records` | `open` | timekeeping_operator, hr_manager | `TimekeepingRecord*` |
| `events` | `/api/v1/events` | `draft` | event_manager | `Event*` |
| `trips` | `/api/v1/travel/trips` | `draft` | event_manager | `Trip*` |
| `notices` | `/api/v1/notices` | `draft` | tenant_owner, institution_director, teacher | `Notice*` |
| `service_requests` | `/api/v1/requests` | `open` | tenant_owner, request_agent, student, guardian, employee | `ServiceRequest*` |
| `automation_rules` | `/api/v1/workflows/rules` | `draft` | tenant_owner | `AutomationRule*` |
| `messages` | `/api/v1/communication/messages` | `draft` | tenant_owner, institution_director, teacher, finance_operator | `Message*` |
| `mailboxes` | `/api/v1/mail/mailboxes` | `requested` | mail_admin, hr_manager | `Mailbox*` |
| `contracts` | `/api/v1/contracts` | `draft` | tenant_owner, secretary, finance_manager, hr_manager | `Contract*` |
| `contract_templates` | `/api/v1/contract-templates` | `draft` | tenant_owner, secretary | `ContractTemplate*` |
| `documents` | `/api/v1/documents` | `draft` | tenant_owner, secretary, teacher, finance_operator | `Document*` |
| `signature_envelopes` | `/api/v1/signature-envelopes` | `draft` | tenant_owner, secretary, guardian, student, employee | `SignatureEnvelope*` |
| `library_items` | `/api/v1/library/items` | `available` | tenant_owner, secretary | `LibraryItem*` |
| `library_loans` | `/api/v1/library/loans` | `active` | tenant_owner, secretary, student, guardian | `LibraryLoan*` |
| `transport_routes` | `/api/v1/transportation/routes` | `draft` | tenant_owner, institution_director | `TransportRoute*` |
| `health_incidents` | `/api/v1/health/incidents` | `open` | tenant_owner, institution_director | `HealthIncident*` |
| `government_exports` | `/api/v1/government-education/exports` | `draft` | tenant_owner, secretary | `GovernmentEducationExport*` |
| `integration_connections` | `/api/v1/integrations/connections` | `draft` | tenant_owner | `IntegrationConnection*` |
| `reports` | `/api/v1/reports` | `requested` | tenant_owner, institution_director, teacher, finance_manager | `Report*` |

Os 47 recursos usam persistência real, autorização, optimistic concurrency, auditoria e outbox no kernel genérico. Isso não significa que todas as particularidades legais de cada domínio estejam homologadas com provedores externos. Planejamento, frequência, branding, App Factory e contratos possuem implementações especializadas além do kernel.
