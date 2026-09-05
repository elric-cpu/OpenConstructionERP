# Daily timekeeping and offline entry

This Gate 2 checkpoint implements:

`Daily Entry → Employee Certification → Supervisor Approval → Preserving Correction`

## Record integrity

Every entry stores the employee, local work date, timezone-aware start/end,
break, calculated total, separate regular/overtime/double-time/travel/leave/
indirect classifications, uncompensated overtime, project and schedule links,
charge/cost/labor codes, trade, location, description, device timestamp, server
receipt timestamp, source, and client operation ID.

The API calculates elapsed hours with decimal arithmetic and rejects a record
unless classified hours equal that total. PostgreSQL repeats the classified
total and nonnegative constraints. Direct project time cannot be entered in the
future; late time requires an explanation; overlapping employee records are
serialized with a tenant/employee/day advisory lock and rejected.

## Certification and approval

- Employees can enter and certify only their linked employee record.
- A self-service employee receives only their own employee option from
  `GET /api/v1/time-entries/resources/employees`; managers with `time.enter_team`
  or `time.read_team` receive the eligible team list.
- Supervisors may create crew drafts but cannot certify for an employee.
- Certification records the employee, timestamp, exact statement, audit event,
  and outbox event.
- Supervisors cannot approve their own time.
- Approval requires a certified record and uses `If-Match` optimistic
  concurrency.
- Certified and approved records have no general update endpoint.

The web page derives its controls from the signed access-token permission
claims. It locks the employee selector to the linked employee for self-service
users, shows certification only for that employee's draft, and shows approval
only with `time.approve_team`. Project and federal charge-code queries are not
issued unless their corresponding read permissions are present. These UI
guards improve clarity; the API remains the authorization boundary.

## Preserving corrections

`POST /api/v1/time-entries/{id}/corrections` requires `If-Match`, a substantive
reason, and a complete replacement record. An employee may correct only their
own time with `time.correct_own`; authorized managers use `time.correct_team`.

The transaction changes the original entry only to `CORRECTED`, creates a new
`DRAFT` replacement, and creates a tenant-scoped `TimeCorrection` that links
both immutable records. The replacement must be certified again by the
employee and approved again by a supervisor. Only then does the correction
become `COMPLETED`. Audit and outbox records share each transition's
correlation ID so payroll and federal labor reporting can reconstruct why,
when, and by whom the record changed.

## Offline operation queue

The PWA stores unsent time operations in IndexedDB with a UUID client operation
ID, original device timestamp, tenant ID, and user ID. Only operations matching
the current authenticated tenant and user are visible or synchronized. Other
users' pending operations remain intact during account switching.

The offline mutation runs independently of TanStack Query's network pause so
the IndexedDB write still executes after the browser reports an outage. Client
operation IDs use the platform UUID generator on secure origins and an RFC 4122
version 4 `crypto.getRandomValues` fallback on non-secure local-development
origins.

The server applies a tenant-scoped unique constraint to the operation ID, so a
retry after a lost response returns the original record instead of duplicating
time. Sync state is always visible, and failed validation leaves the operation
queued for human correction rather than silently discarding it.

The service worker caches only the application shell and static assets. API
responses containing business data are deliberately excluded from the shared
cache; authorized field datasets will use tenant/user-scoped IndexedDB stores.

Real-stack Playwright acceptance verifies queue visibility, reconnect sync, and
server-side duplicate prevention in Chromium, Firefox, WebKit, and a Pixel 7
mobile Chromium profile.
