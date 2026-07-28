from datetime import date, timedelta
from typing import Any

from .onboarding_domain import ComplianceRequirement, EmployeeCreate

RULE_VERSION = "2026-07-16.2.pending-legal-review"


ONBOARDING_REQUIREMENTS = [
    ComplianceRequirement(
        id="form-i9",
        label="Form I-9 employee attestation",
        responsible_party="employee",
        applicability="Every employee hired to work for pay in the United States.",
        trigger="Employee accepts an offer and no later than the first day of work.",
        task_owner="employee",
        completion_method="document_upload",
        retention_rule=(
            "Retain for three years after hire or one year after employment ends, "
            "whichever is later."
        ),
        data_classification="highly_restricted",
        data_category="identity_i9",
        official_source=(
            "https://www.uscis.gov/sites/default/files/document/forms/i-9.pdf"
        ),
    ),
    ComplianceRequirement(
        id="form-i9-employer-review",
        label="Form I-9 employer document review",
        responsible_party="employer",
        applicability="Every employee hired to work for pay in the United States.",
        trigger="After the employee completes Section 1; generally within three business days of hire.",
        task_owner="employer",
        completion_method="employer_evidence",
        retention_rule=(
            "Retain with Form I-9 for three years after hire or one year after "
            "employment ends, whichever is later."
        ),
        data_classification="highly_restricted",
        data_category="identity_i9",
        official_source=(
            "https://www.uscis.gov/sites/default/files/document/forms/i-9.pdf"
        ),
    ),
    ComplianceRequirement(
        id="e-verify",
        label="E-Verify or E-Verify+ case",
        responsible_party="employer",
        applicability=(
            "Only when Benson is enrolled or the governing contract or subcontract "
            "contains the FAR E-Verify clause."
        ),
        trigger="Qualified review confirms program enrollment or a covered FAR clause.",
        task_owner="employer",
        completion_method="employer_evidence",
        retention_rule=(
            "Follow the current E-Verify MOU and retain the case result with the "
            "related Form I-9 record."
        ),
        data_classification="highly_restricted",
        data_category="identity_i9",
        official_source="https://www.e-verify.gov/employers/federal-contractors",
    ),
    ComplianceRequirement(
        id="federal-w4",
        label="Federal Form W-4",
        responsible_party="employee",
        applicability="Every employee; not an independent-contractor form.",
        trigger="Employee hire, before the first wage payment.",
        task_owner="employee",
        completion_method="document_upload",
        retention_rule=(
            "Keep the signed certificate while effective and for the applicable "
            "employment-tax record period."
        ),
        data_classification="highly_restricted",
        data_category="tax",
        official_source="https://www.irs.gov/pub/irs-pdf/fw4.pdf",
    ),
    ComplianceRequirement(
        id="oregon-w4",
        label="Oregon Form OR-W-4",
        responsible_party="employee",
        applicability="Employees whose wages are subject to Oregon withholding.",
        trigger="Oregon employee hire or a later withholding election change.",
        task_owner="employee",
        completion_method="document_upload",
        retention_rule="Retain the effective certificate with payroll tax records.",
        data_classification="highly_restricted",
        data_category="tax",
        official_source=(
            "https://www.oregon.gov/dor/forms/FormsPubs/form-or-W-4_101-402_2026.pdf"
        ),
    ),
    ComplianceRequirement(
        id="oregon-new-hire-report",
        label="Oregon new-hire report",
        responsible_party="employer",
        applicability="Employees and reportable rehires working for an Oregon employer.",
        trigger="Hire or rehire; report within the applicable Oregon deadline.",
        task_owner="employer",
        completion_method="employer_evidence",
        retention_rule=(
            "Retain the submission confirmation under the approved payroll record schedule."
        ),
        data_classification="highly_restricted",
        data_category="tax",
        official_source="https://sos.oregon.gov/business/Pages/employer-forms.aspx",
    ),
    ComplianceRequirement(
        id="payroll-enrollment",
        label="Payroll enrollment",
        responsible_party="employee",
        applicability="Employees paid through Benson payroll.",
        trigger="Employee hire before payroll processing.",
        task_owner="employee",
        completion_method="document_upload",
        retention_rule="Retain under the approved payroll and employment-tax schedule.",
        data_classification="highly_restricted",
        data_category="tax",
        official_source="https://www.irs.gov/publications/p15",
    ),
    ComplianceRequirement(
        id="payment-election",
        label="Payroll payment election",
        responsible_party="employee",
        applicability=(
            "Employees; direct deposit must remain optional and a no-cost alternative "
            "must remain available."
        ),
        trigger="Employee hire or later payment-method change.",
        task_owner="employee",
        completion_method="document_upload",
        retention_rule="Retain the effective authorization under the payroll schedule.",
        data_classification="highly_restricted",
        data_category="banking",
        official_source="https://www.oregon.gov/boli/workers/Pages/paychecks.aspx",
    ),
    ComplianceRequirement(
        id="emergency-contact",
        label="Emergency contact record",
        responsible_party="employee",
        applicability="Benson employee onboarding policy; not represented as a legal mandate.",
        trigger="Employee hire and later contact changes.",
        task_owner="employee",
        completion_method="manual_review",
        retention_rule="Retain while current; supersede stale contact details.",
        data_classification="confidential",
        data_category="general",
        official_source="benson-policy://emergency-contact-record",
    ),
    ComplianceRequirement(
        id="company-policies",
        label="Company policy acknowledgement",
        responsible_party="employee",
        applicability="All Benson employees receiving the approved handbook.",
        trigger="Employee hire and each approved material policy revision.",
        task_owner="employee",
        completion_method="employee_signature",
        retention_rule="Retain the signed acknowledgement with the personnel record.",
        data_classification="confidential",
        data_category="general",
        official_source="benson-policy://employee-handbook",
    ),
    ComplianceRequirement(
        id="safety-orientation",
        label="Construction safety orientation acknowledgement",
        responsible_party="employee",
        applicability="Employees exposed to Benson construction work environments.",
        trigger="Before assignment to covered work and when hazards or duties change.",
        task_owner="employee",
        completion_method="employee_signature",
        retention_rule="Retain training and acknowledgement records under the safety schedule.",
        data_classification="confidential",
        data_category="general",
        official_source=(
            "https://www.osha.gov/laws-regs/regulations/standardnumber/1926/1926.21"
        ),
    ),
    ComplianceRequirement(
        id="davis-bacon",
        label="Davis-Bacon classification and certified-payroll setup",
        responsible_party="employer",
        applicability=(
            "Workers on a contract or subcontract actually covered by DBRA clauses "
            "and the incorporated wage determination."
        ),
        trigger="Qualified contract review confirms covered work before assignment.",
        task_owner="employer",
        completion_method="employer_evidence",
        retention_rule=(
            "Retain covered contract, payroll, apprenticeship, and supporting records "
            "for the legally approved period."
        ),
        data_classification="restricted",
        data_category="tax",
        official_source="https://www.dol.gov/agencies/whd/forms/wh347",
    ),
    ComplianceRequirement(
        id="section-503-self-id",
        label="Section 503 voluntary disability self-identification invitation",
        responsible_party="employee",
        applicability=(
            "Only when qualified review confirms current Section 503 jurisdiction; "
            "current OFCCP thresholds must be checked at decision time."
        ),
        trigger="Covered post-offer stage and other required invitation cycles.",
        task_owner="employee",
        completion_method="document_upload",
        retention_rule=(
            "Segregate voluntary self-identification data and retain under the approved "
            "OFCCP schedule."
        ),
        data_classification="highly_restricted",
        data_category="medical_disability",
        official_source=(
            "https://www.dol.gov/sites/dolgov/files/OFCCP/regs/compliance/"
            "sec503/Self_ID_Forms/503Self-IDForm.pdf"
        ),
    ),
    ComplianceRequirement(
        id="vevraa-self-id",
        label="VEVRAA protected-veteran self-identification invitation",
        responsible_party="employee",
        applicability=(
            "Only when qualified review confirms current VEVRAA jurisdiction; current "
            "OFCCP thresholds must be checked at decision time."
        ),
        trigger="Covered pre-offer or post-offer stage as applicable.",
        task_owner="employee",
        completion_method="document_upload",
        retention_rule=(
            "Segregate voluntary self-identification data and retain under the approved "
            "OFCCP schedule."
        ),
        data_classification="highly_restricted",
        data_category="veteran",
        official_source="https://www.dol.gov/agencies/ofccp/vevraa/self-id-form",
    ),
    ComplianceRequirement(
        id="contractor-w9",
        label="Form W-9",
        responsible_party="contractor",
        applicability=(
            "Only for a genuine independent contractor after worker classification is approved."
        ),
        trigger="Approved contractor engagement before reportable payment.",
        task_owner="contractor",
        completion_method="document_upload",
        retention_rule="Retain with information-return and backup-withholding records.",
        data_classification="highly_restricted",
        data_category="tax",
        official_source="https://www.irs.gov/forms-pubs/about-form-w-9",
    ),
]

REQUIREMENTS_BY_ID = {item.id: item for item in ONBOARDING_REQUIREMENTS}


def _business_days_after(start: date, days: int) -> date:
    due = start
    remaining = days
    while remaining:
        due += timedelta(days=1)
        if due.weekday() < 5:
            remaining -= 1
    return due


def _task(
    requirement_id: str,
    *,
    label: str,
    instructions: str,
    applicability_reason: str,
    due_date: date,
    status: str = "pending",
    applicability_status: str = "applied",
    applicability_review_required: bool = False,
    signature_statement: str | None = None,
) -> dict[str, Any]:
    requirement = REQUIREMENTS_BY_ID[requirement_id]
    return {
        "requirement_id": requirement_id,
        "label": label,
        "responsible_party": requirement.task_owner,
        "status": status,
        "due_date": due_date,
        "instructions": instructions,
        "applicability_reason": applicability_reason,
        "evidence_required": requirement.completion_method != "manual_review",
        "completion_method": requirement.completion_method,
        "applicability_review_required": applicability_review_required,
        "applicability_status": applicability_status,
        "retention_rule": requirement.retention_rule,
        "data_classification": requirement.data_classification,
        "data_category": requirement.data_category,
        "official_source": requirement.official_source,
        "legal_review_status": requirement.legal_review_status,
        "signature_statement": signature_statement,
    }


def initial_employee_tasks(employee: EmployeeCreate) -> list[dict[str, Any]]:
    if employee.classification == "independent_contractor":
        return [
            _task(
                "contractor-w9",
                label="Complete Form W-9",
                instructions=(
                    "Complete the current Form W-9 for Benson's information-return records."
                ),
                applicability_reason=(
                    "Worker is classified as a genuine independent contractor."
                ),
                due_date=employee.start_date,
            )
        ]

    tasks = [
        _task(
            "form-i9",
            label="Complete Form I-9 employee section",
            instructions=(
                "Complete Section 1 through the approved I-9 workflow no later than "
                "your first day. Do not email identity documents."
            ),
            applicability_reason="Required for a U.S. employee hire.",
            due_date=employee.start_date,
        ),
        _task(
            "form-i9-employer-review",
            label="Complete Form I-9 employer document review",
            instructions=(
                "Benson's authorized representative must inspect acceptable documents "
                "and complete the employer review through the approved I-9 workflow."
            ),
            applicability_reason="Required for a U.S. employee hire.",
            due_date=_business_days_after(employee.start_date, 3),
        ),
        _task(
            "federal-w4",
            label="Complete federal Form W-4",
            instructions="Complete the current IRS Form W-4 for federal withholding.",
            applicability_reason="Worker is an employee.",
            due_date=employee.start_date,
        ),
        _task(
            "oregon-w4",
            label="Complete Oregon Form OR-W-4",
            instructions="Complete the current Oregon Form OR-W-4 for withholding.",
            applicability_reason="Initial work location is in Oregon.",
            due_date=employee.start_date,
        ),
        _task(
            "oregon-new-hire-report",
            label="Submit Oregon new-hire report",
            instructions=(
                "Benson payroll staff must submit the report and retain confirmation."
            ),
            applicability_reason="Oregon employee hire.",
            due_date=employee.start_date + timedelta(days=20),
        ),
        _task(
            "payroll-enrollment",
            label="Complete payroll enrollment",
            instructions="Provide payroll details only through the protected workflow.",
            applicability_reason="Worker is an employee paid through payroll.",
            due_date=employee.start_date,
        ),
        _task(
            "payment-election",
            label="Choose a payroll payment method",
            instructions=(
                "Choose direct deposit or Benson's no-cost lawful alternative. Direct "
                "deposit is optional."
            ),
            applicability_reason="A payroll payment method is required.",
            due_date=employee.start_date,
        ),
        _task(
            "emergency-contact",
            label="Provide an emergency contact",
            instructions=(
                "Provide a current contact through the protected HR workflow; do not "
                "place personal details in a review comment."
            ),
            applicability_reason="Benson employee onboarding policy.",
            due_date=employee.start_date,
        ),
        _task(
            "company-policies",
            label="Review and acknowledge company policies",
            instructions=(
                "Review the approved employee handbook before signing this acknowledgement."
            ),
            applicability_reason="Benson employee onboarding policy.",
            due_date=employee.start_date,
            signature_statement=(
                "I acknowledge that I received and reviewed the Benson employee handbook "
                "version identified by this task."
            ),
        ),
        _task(
            "safety-orientation",
            label="Complete construction safety orientation",
            instructions=(
                "Complete the role-appropriate orientation before signing this record."
            ),
            applicability_reason="Benson construction safety onboarding requirement.",
            due_date=employee.start_date,
            signature_statement=(
                "I attest that I completed the Benson construction safety orientation "
                "assigned for my initial role and had an opportunity to ask questions."
            ),
        ),
    ]
    federal_not_applicable = employee.federal_contract_applicability == "not_applicable"
    for requirement_id, label in (
        ("e-verify", "Complete applicable E-Verify/E-Verify+ case"),
        ("davis-bacon", "Confirm Davis-Bacon classification and payroll setup"),
        ("section-503-self-id", "Issue applicable Section 503 invitation"),
        ("vevraa-self-id", "Issue applicable VEVRAA invitation"),
    ):
        tasks.append(
            _task(
                requirement_id,
                label=label,
                instructions=(
                    "Qualified HR/legal review must confirm the governing contract, "
                    "current threshold, and task applicability before this task opens."
                ),
                applicability_reason=(
                    "Owner marked federal-contract requirements not applicable at creation."
                    if federal_not_applicable
                    else "Federal-contract applicability requires qualified review."
                ),
                due_date=employee.start_date,
                status="not_applicable" if federal_not_applicable else "blocked",
                applicability_status=(
                    "not_applicable" if federal_not_applicable else "pending_review"
                ),
                applicability_review_required=not federal_not_applicable,
            )
        )
    return tasks
