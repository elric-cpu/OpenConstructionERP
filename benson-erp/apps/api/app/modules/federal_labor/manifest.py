MODULE = {
    "name": "federal_labor",
    "depends_on": ("platform", "people", "projects", "timekeeping", "payroll"),
    "permissions": (
        "federal_labor.charge_codes_manage",
        "federal_labor.charge_codes_read",
        "federal_labor.rates_manage",
        "federal_labor.qualifications_manage",
        "federal_labor.invoice_support_generate",
        "federal_labor.invoice_support_read",
        "federal_labor.floor_check_read",
    ),
    "events": (
        "FederalChargeCodeClosed",
        "FederalInvoiceSupportGenerated",
        "EmployeeQualificationChanged",
    ),
}
