# Full ERP completion matrix

This matrix prevents a completed vertical slice from being mistaken for the
full Benson ERP outcome. A module is complete only when persistence, server
authorization, attributable audit, responsive UI, tests, UAT, backup/restore,
rollback, and approved production smoke evidence all exist.

| Workflow | Current evidence | Remaining gate |
| --- | --- | --- |
| Leads | Production lead queue, signed intake, private attachments, audit | Include in end-to-end lead-to-cash UAT |
| Customers | Persisted guarded workflow and automated tests | Candidate deploy, synthetic UAT, backup/restore proof |
| Employees/onboarding | Invite, Tasks, encrypted evidence, conditional rules | Full rejection/resubmission/offboarding UAT and HR/legal approvals |
| Estimates | Persisted guarded workflow and automated tests | Candidate deploy, synthetic delivery/decision UAT, backup/restore proof |
| Jobs | Not implemented in Benson overlay | Full vertical slice |
| Schedule | Not implemented in Benson overlay | Full vertical slice |
| Field records | Not implemented in Benson overlay | Full vertical slice |
| Change orders | Not implemented in Benson overlay | Full vertical slice |
| Invoices/payments | Not implemented in Benson overlay | Full vertical slice; no money movement without approval |
| Accounting/reporting | Provider boundary only | Persisted workflow, controlled integration, reconciliation |
| Settings | Notification settings implemented | Complete role/settings surface and UAT |
| Release | Prior lead/onboarding production revision exists | Full-scope candidate, rollback, approved cutover, smoke |

Qualified HR/legal approval of the onboarding matrix and forms remains an
external completion gate. Code and automated tests cannot supply that approval.
