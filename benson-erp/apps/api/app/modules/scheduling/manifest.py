MODULE = {
    "name": "scheduling",
    "depends_on": ("platform", "people", "projects"),
    "permissions": ("schedules.read", "schedules.read_own", "schedules.manage"),
    "events": ("ScheduleCreated", "ScheduleActivityCreated", "EmployeeScheduled"),
}
