# Native employee scheduling

The Gate 2 scheduling checkpoint connects projects to employees through three
tenant-scoped records:

`Project → Schedule → Schedule Activity → Employee Assignment`

Each project has one canonical schedule. Activities store timezone-aware start
and end timestamps, site/location details, required tools, and a lifecycle
status. Assignments link an eligible employee to an activity and retain the
manager's reason in the audit record.

## Authorization

- `schedules.manage` creates schedules, activities, and assignments.
- `schedules.read` reads the tenant dispatch calendar.
- `schedules.read_own` reads only the schedule linked to the authenticated
  employee profile. A caller cannot expand this scope by submitting another
  employee ID.
- `projects.read` supplies the manager's project selector.

Every repository query carries `tenant_id`, and PostgreSQL FORCE RLS protects
the schedule, activity, and assignment tables. Composite foreign keys prevent
an activity or assignment from linking records across tenants.

## Concurrency and conflicts

Schedule and activity mutations require `If-Match` versions. Assignment uses a
transaction-scoped PostgreSQL advisory lock derived from tenant and employee,
then checks all non-cancelled activities for an overlapping time window. This
serializes concurrent dispatch attempts for the same employee and returns a
409 conflict rather than double-booking them.

Creating a schedule, activity, or assignment writes its audit record and
transactional outbox event in the same database transaction. Events are
`ScheduleCreated`, `ScheduleActivityCreated`, and `EmployeeScheduled`.

## Timekeeping dependency

Time entries may reference the schedule assignment that dispatched the work.
The assignment does not generate or certify time automatically: employees must
still enter all actual direct and indirect hours, certify their own records,
and preserve corrections through adjusting entries. A self-service employee's
`schedules.read_own` grant exposes only their linked assignments; it does not
grant access to the tenant dispatch board.
