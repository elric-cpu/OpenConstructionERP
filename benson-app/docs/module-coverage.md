# Benson ERP module coverage

This repository is the Benson operations application, not a silent claim that
the upstream OpenConstructionERP 120+ module catalog has been copied into the
Benson UI. Upstream documents BOQ, cost database, CAD/BIM takeoff, AI
estimation, planning, procurement, finance, safety, inspections, NCR,
submittals, correspondence, CDE, transmittals, BIM Hub, reporting,
notifications, comments, Gantt, regional settings, module configuration,
regional packs, and import/export.

The Benson build currently exposes working product areas for leads/CRM,
customers, estimates, accepted-estimate-to-job conversion, jobs, schedule,
field records, change orders, staff onboarding, W-4/I-9-related task
assignments, protected documents, signatures, audited Google identity
provisioning, notifications, audit history, operations agent, and accounting
foundations.

Before calling this a full upstream parity release, each upstream module needs
an explicit route, authenticated permission test, visible navigation entry,
create/edit action, empty state, and API smoke test. Missing modules must be
labelled planned rather than represented by a dead menu item.
