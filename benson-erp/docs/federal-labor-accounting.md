# Federal labor accounting

This Gate 2 checkpoint connects canonical federal charge codes to daily time,
date-effective employee qualifications, contract billing rates, floor-check
evidence, and immutable labor invoice support.

## Authoritative hierarchy and time controls

Federal charge codes snapshot the configured agency, contract, task or delivery
order, CLIN/SLIN, funding line, project, cost code, and labor category. A field
employee selects one open code; the API rejects conflicting submitted values
and writes the canonical hierarchy to the time entry. Closed or out-of-period
codes and missing date-effective qualifications are blocked.

The hierarchy is not a substitute for contract review. Contract administrators
must configure the applicable profile, wage determination, labor category,
qualification, and authorized period from the actual award documents.

## Billing-rate separation

Federal contract bill rates are stored separately from employee pay rates,
actual payroll cost, and provider-paid results. Each effective rate preserves
regular, overtime, and double-time values. Invoice support calculates each line:

```text
regular hours × regular bill rate
+ overtime hours × overtime bill rate
+ double-time hours × double-time bill rate
```

Each line is rounded half-up to USD cents. Travel, leave, and indirect hours are
excluded unless a future authorized classification/rate explicitly supports
them; travel is a blocking exception rather than being silently discarded.

## Floor checks and invoice support

The floor-check endpoint includes draft, certified, and approved federal time
so missing certification or approval remains visible. It answers who worked,
where, what they recorded, the contract/task/CLIN/labor category, who approved
the time, and whether linked payroll results and invoice-support lines exist.

Invoice preview reports blocking exceptions for missing rates, qualifications,
or inconsistent canonical snapshots. Generation requires a clean preview and
creates a checksummed, versioned artifact containing:

- source time approval and employee-certification versions;
- date-effective bill-rate version and formula;
- qualification evidence/version;
- payroll result and reconciliation linkage;
- separate regular, overtime, and double-time hours and rates.

Generated headers and lines are protected from update and deletion by database
triggers. A repeated identical generation is rejected; a changed source
snapshot creates the next immutable artifact version.

## Permissions

- `federal_labor.charge_codes_read`
- `federal_labor.charge_codes_manage`
- `federal_labor.rates_manage`
- `federal_labor.qualifications_manage`
- `federal_labor.floor_check_read`
- `federal_labor.invoice_support_read`
- `federal_labor.invoice_support_generate`

Forced PostgreSQL RLS applies to every federal-labor table, and all repository
joins include the tenant key.

## Compliance boundary

These controls provide traceability; they do not determine allowability,
prevailing-wage coverage, Service Contract Labor Standards coverage, or invoice
eligibility. A qualified contracts/payroll professional must review each
contract, incorporated clauses, wage determination, collective-bargaining
agreement, jurisdiction, and current agency guidance.

Remaining Gate 2 work includes certified-payroll statements, correction-driven
adjustment exports and federal invoice adjustments, provider-specific
transmission/result connectors, and browser acceptance for the complete second
vertical slice.
