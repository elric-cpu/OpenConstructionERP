MODULE = {
    "name": "timekeeping",
    "depends_on": ("platform", "people", "projects", "scheduling"),
    "permissions": (
        "time.enter_own",
        "time.enter_team",
        "time.certify_own",
        "time.approve_team",
        "time.read_team",
        "time.correct_own",
        "time.correct_team",
    ),
    "events": (
        "TimeEntryCreated",
        "TimeEntryCertified",
        "TimeEntryApproved",
        "TimeCorrectionRequested",
        "TimeCorrectionCompleted",
    ),
}
