MODULE = {
    "name": "payroll",
    "depends_on": ("platform", "people", "projects", "timekeeping"),
    "permissions": (
        "payroll.periods_manage",
        "payroll.review",
        "payroll.export",
        "payroll.view_wages",
        "payroll.mappings_manage",
    ),
    "events": ("PayrollPeriodLocked", "PayrollExportGenerated"),
}
