# Benson Three-Way Capability Matrix

This matrix is the release ledger for the upstream-additive integration. The
`benson-app/` and `benson-erp/` trees remain immutable references until every
row has passed its integrated acceptance evidence.

| Capability | Upstream v12.9.0 foundation | `benson-app/` reference | `benson-erp/` reference | Integrated owner | Acceptance evidence |
|---|---|---|---|---|---|
| Identity and roles | `users`, `admin` | auth and employee stores | `people`, `platform` | `benson_workforce`, `benson_security` | Upstream user/admin suites plus `backend/tests/unit/test_benson_edition.py` |
| CRM lead-to-project | `crm`, `projects` | lead, customer, estimate, and job routes | `crm`, `estimating`, `projects` | `benson_operations` | Upstream CRM/project suites; archived lead-to-project journey retained |
| Estimating | `boq`, `costs`, `assemblies` | estimate routes and workspace | `estimating` | `benson_operations` | Unchanged upstream BOQ/cost/assembly suites |
| Immutable documents | `documents`, `signing`, audit core | object storage and signing | `documents` | `benson_operations`, `benson_security` | Unchanged upstream document/signing/audit suites |
| Scheduling | `schedule`, `schedule_advanced` | schedule routes and workspace | `scheduling` | `benson_operations` | Unchanged upstream schedule suites |
| Offline timekeeping | `field_time`, PWA runtime | operations web reference | `timekeeping` offline queue | `benson_workforce` | Upstream field-time/PWA suites; archived queue tests retained |
| Employee onboarding | `onboarding`, `users` | onboarding and new-hire workspace | `people`, activation route | `benson_workforce` | Upstream onboarding suites; archived activation tests retained |
| Federal labor | `compliance`, `payroll` | compliance policy | `federal_labor` | `benson_workforce` | Upstream compliance/payroll suites; archived federal-labor tests retained |
| Payroll | `payroll`, `finance` | accounting provider | `payroll` | `benson_finance`, `benson_workforce` | Unchanged upstream payroll/finance suites; archived payroll tests retained |
| Reconciliation | `reconciliation`, `finance` | integration audit | payroll reconciliation | `benson_finance` | Unchanged upstream reconciliation suites |
| MFA | `users`, `admin` | Google identity | `platform.mfa_service` | `benson_security` | Unchanged upstream authentication/security suites |
| Audit | audit core, `activity_log` | integration and lead audit | people/platform audit | `benson_security` | Unchanged upstream audit suites |
| Workers and providers | `jobs`, `notifications`, Celery core | provider integrations | worker registry and tasks | `benson_workers` | Unchanged upstream job/notification/worker suites |

No row replaces its upstream foundation. Each Benson owner is an adapter and
policy layer, while the source feature remains registered and tested unchanged.
