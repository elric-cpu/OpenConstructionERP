# Benson onboarding compliance matrix

Status: **Pending qualified HR/legal review. Do not use this draft as a legal-compliance certification.**

The API exposes the machine-readable matrix at `GET /api/benson/v1/onboarding/requirements`. Every rule is conditional on worker classification, work location, contract clauses, contract value, and the applicable wage determination. Direct deposit is an optional payment election, not a universal legal prerequisite. Form W-2 is issued by the employer after the tax year and is not a new-hire task.

## Workspace identity and license boundary

Employees sign in with an `@bensonhomesolutions.com` Google identity, but onboarding must never assign a paid Google Workspace license. Account creation is an approval-gated external action. Until automated provisioning is independently verified, an administrator must create the identity in an organizational unit where paid automatic licensing is disabled and confirm that no paid license was assigned. The portal records `no_paid_license` as policy; it does not treat a successful Directory API user creation as proof of license state. Invitations use a separate reachable delivery email so onboarding does not depend on the unlicensed identity having a mailbox.

| Requirement | Applies when | Owner | Data | Official source |
| --- | --- | --- | --- | --- |
| Form I-9 | Employee hired for U.S. work | Employee and employer | Restricted | [USCIS I-9 Central](https://www.uscis.gov/i-9-central/retain-and-store-form-i-9) |
| E-Verify / E-Verify+ | Enrollment or a covered contract/subcontract with the FAR clause | Employer | Restricted | [E-Verify federal contractors](https://www.e-verify.gov/employers/federal-contractors) |
| Federal W-4 | Employee | Employee | Restricted | [IRS hiring employees](https://www.irs.gov/businesses/small-businesses-self-employed/hiring-employees) |
| Oregon OR-W-4 | Wages subject to Oregon withholding | Employee | Restricted | [Oregon withholding](https://www.oregon.gov/dor/programs/businesses/pages/withholding-and-payroll-tax.aspx) |
| Oregon new-hire report | Reportable Oregon employee | Employer | Restricted | [Oregon employer forms](https://sos.oregon.gov/business/Pages/employer-forms.aspx) |
| Payroll and payment election | Employee | Employee and employer | Restricted | [IRS Publication 15](https://www.irs.gov/publications/p15) |
| Davis-Bacon setup | Contract/subcontract covered by DBRA clauses and a wage determination | Employer | Restricted | [DOL WH-347 instructions](https://www.dol.gov/agencies/whd/forms/wh347) |
| Section 503 invitation | Current OFCCP jurisdiction applies | Employee | Restricted and segregated | [OFCCP self-ID forms](https://www.dol.gov/agencies/ofccp/self-id-forms) |
| VEVRAA invitation | Current OFCCP jurisdiction applies | Employee | Restricted and segregated | [OFCCP VEVRAA FAQ](https://www.dol.gov/agencies/ofccp/faqs/vevraa) |
| Form W-9 | Approved genuine independent contractor | Contractor | Restricted | [IRS Form W-9](https://www.irs.gov/forms-pubs/about-form-w-9) |

Before approval, counsel/HR must confirm current thresholds, clauses, deadlines, retention periods, required notices, Oregon paid-leave/workers-comp requirements, and company-specific policy acknowledgements. The product must preserve the source version and reviewer for every approved rule change.
