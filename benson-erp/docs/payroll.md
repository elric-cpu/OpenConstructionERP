# Payroll periods, exports, and reconciliation

The payroll module converts approved daily time into immutable provider artifacts
and then reconciles provider-paid results back to source time and project labor
cost. PostgreSQL remains authoritative; spreadsheet files are interchange
artifacts, never the production database.

## Workflow and controls

1. Create a non-overlapping payroll period and advance it through employee,
   supervisor, and payroll review.
2. Resolve preview exceptions. The lock is blocked by unapproved time, missing
   employee/earning/project/cost/labor mappings, missing date-effective pay
   rates, or incomplete wage classifications.
3. Lock the period. The lock stores an explainable validation snapshot and
   cannot silently change source time.
4. Generate CSV, XLSX, or JSON. Each format is an immutable artifact with a
   SHA-256 checksum, source-line snapshots, date-effective mapping versions,
   and pay-rate version. Duplicate format/version generation is rejected.
5. Import provider results against one specific export. Each result row must
   identify the source `time_entry_id`; unknown and duplicate source rows are
   rejected.
6. Review persisted reconciliation exceptions. Resolving an exception requires
   `payroll.reconcile`, an optimistic `If-Match` version, and a substantive
   reason in the audit log.
7. Reconcile. Open exceptions block posting. A clean or reviewed import creates
   immutable project labor-cost rows and moves the period to `RECONCILED`.

The project labor-cost calculation is:

```text
gross wages
+ employer taxes
+ employer benefits
+ workers compensation
+ fringe benefits
```

Every posted row links provider result → export line → approved time entry →
employee/project/cost code. Employee deductions and net pay are retained for
payroll reconciliation but are not added to employer job cost.

## Authorization and sensitive data

- `payroll.review` reads periods and validation previews.
- `payroll.periods_manage` creates and advances periods.
- `payroll.mappings_manage` maintains provider mappings.
- `payroll.export` generates and downloads artifacts.
- `payroll.import` imports provider-paid results.
- `payroll.reconcile` reviews exceptions and posts project labor cost.
- `payroll.view_wages` is additionally required for pay rates, sensitive
  artifacts, result imports, reconciliation detail, and job-cost totals.

Tenant RLS is forced on periods, rates, mappings, exports, result imports,
result lines, exceptions, and job-cost rows. Client-visible APIs never infer
wage access from a broader accounting or project permission.

## Provider boundary

The provider-neutral adapter contract supports validation, artifact building,
transmission, result import, and reconciliation. Current adapters generate the
controlled schema for Generic, QuickBooks Payroll, ADP, Gusto, Paychex,
Rippling, UKG, Sage, construction-payroll, and custom configurations.
Transmission and provider-specific result connectors remain disabled until
approved credentials and mappings are configured; the UI currently accepts a
controlled JSON provider-result payload.

## Compliance assumptions and remaining work

Payroll calculations in this module are reconciliation and job-cost controls,
not a tax engine or legal determination. State overtime, union, prevailing-wage,
certified-payroll, tax withholding, benefit, and final-pay rules must be
configured and reviewed by qualified payroll/legal professionals for each
jurisdiction and contract.

Federal floor-check reporting and immutable labor invoice support are described
in `federal-labor-accounting.md`. Still required for the complete second
vertical slice: adjustment exports after post-export time corrections,
provider-specific file/API schemas beyond the controlled generic schema,
general-ledger posting, certified-payroll statements, complete browser
acceptance, and production credentialed provider integrations.
