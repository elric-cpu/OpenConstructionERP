MODULE = {
    "name": "people",
    "depends_on": ("platform",),
    "permissions": ("employees.manage", "employees.approve", "employees.activate"),
    "events": (
        "EmployeeCreated",
        "EmployeeProvisioningRequested",
        "GoogleIdentityCreated",
        "EmployeeActivationRequested",
        "EmployeeActivationSent",
        "EmployeeActivated",
        "EmployeeActivationRevoked",
    ),
}
