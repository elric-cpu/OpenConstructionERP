# Full ERP completion matrix

This matrix prevents implemented code, an old production revision, or one green
test suite from being mistaken for the completed Benson ERP. Completion requires
persistence, server authorization, attributable audit, responsive UI, automated
tests, isolated staging UAT, backup restoration, rollback, external approvals,
and recorded production smoke evidence.

| Workflow | Current repository evidence | Remaining release gate |
| --- | --- | --- |
| Leads | Signed intake, durable notifications, private attachments, audit, production history | Current-digest lead-to-cash UAT and restore proof |
| Customers | Persisted guarded workflow and API/browser tests | Current-digest staging UAT and restore proof |
| Estimates | Persisted guarded workflow and API/browser tests | Delivery/decision UAT and restore proof |
| Jobs | Accepted-estimate conversion, guarded states, assignment policy, tests | Delivery UAT and restore proof |
| Schedule | Race-safe persisted workflow and responsive API/browser coverage | Authenticated staging UAT and restore proof |
| Field records | Versioned reports, corrections, private photos, assignment scoping, tests | Full gate, candidate, staging/mobile UAT, and restore proof |
| Change orders | Guarded revisions, evidence, approval effects, billing-eligibility controls, tests | Full gate, candidate, staging concurrency/UAT, and restore proof |
| Invoices/payments | Not implemented in the Benson overlay | Full slice; Stripe test mode only until approved cutover |
| Accounting/reporting | Provider boundary only | Balanced ledger, reports, outbox/conflicts, sandbox reconciliation |
| Employees/onboarding | Invitation, Tasks, conditional rules, encrypted evidence | Provisioning, reviews, offboarding, staging UAT, HR/legal approval |
| Settings/integrations | Notification settings and provider boundaries | Explicit route capabilities, health, consent, secrets/IAM UAT |
| Release | Live `benson-operations` history and retained rollback/export evidence | Isolated staging, immutable full-scope digest, G1–G8 evidence |

## Current release decision

The release is **NO-GO**. Billing, accounting, full onboarding, isolated staging,
current backup restoration, qualified HR/legal approval, and a current immutable
candidate do not yet exist as recorded evidence. Twilio remains disabled. No
production traffic change, real payment, accounting-provider production write, or real
employee invitation may occur merely because an individual module passes.
