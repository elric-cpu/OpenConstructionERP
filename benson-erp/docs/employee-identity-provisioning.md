# Employee identity provisioning

The Gate 2 identity segment implements:

`Employee Draft → Manager Approved → Google Identity Requested → Identity Created → Activation Email Sent → ERP Access Confirmed → Active`

Approval is an optimistic, transactional operation. It updates the employee,
creates one tenant-scoped provisioning request, records the reason in the audit
log, and writes `EmployeeProvisioningRequested` to the transactional outbox.
The durable worker owns the provider call. Replaying an event returns the
existing Directory user and cannot create a second identity.

## Identity policy

- The account is company-managed and no paid Google Workspace license is
  assigned.
- Google requires a temporary password for user creation. The worker generates
  it in memory and sends it only to Google with
  `changePasswordAtNextLogin=true`; it is never persisted, logged, or emailed.
- The Directory account and ERP credential are separate. After Directory
  creation, the worker issues a random, tenant-bound, single-use ERP activation
  token. Only its SHA-256 hash is stored for validation; the delivery secret is
  encrypted at rest until delivery and cleared after SMTP delivery.
- Permanent passwords and Google temporary passwords are never sent by email.
- Provider responses store only the Directory subject ID and primary email.

## ERP activation

The activation email goes only to the employee's personal address and contains
the company username, Google sign-in link, ERP sign-in link, expiration time,
support details, and the notice that Gmail may be unavailable for an unlicensed
Cloud Identity account. The activation URL places the token in the URL fragment
so it is not sent in HTTP request logs; the browser removes the fragment from
history immediately and submits the token only in the API request body.

Activation creates or safely links an uncredentialed ERP user, grants the
least-privilege employee self-service permission set, records the employee-user
link, consumes the token, revokes older tenant sessions, and requires a normal
login with the new password. Expired, revoked, used, malformed, and cross-tenant
tokens return the same safe response. Reissuing activation revokes all earlier
unused requests and is an audited, optimistic operation.

The employee self-service membership contains only:

- `projects.read`;
- `schedules.read_own`;
- `time.enter_own`;
- `time.certify_own`;
- `time.correct_own`.

It does not grant employee administration, team-time approval, payroll, wage,
or federal charge-code administration. The daily-time resource endpoint returns
only the linked employee unless the caller has team-time permission, and the
schedule service applies the same linked-employee boundary.

## Manager operations

`employees.activate` authorizes activation reissue and local preview. Existing
administrators with `employees.manage` are compatible and may perform the same
operations. Reissue requires the employee's current version in `If-Match` and a
substantive reason:

```text
POST /api/v1/employees/{employee_id}/activation/reissue
If-Match: {employee_version}
```

The employee screen shows invitation and ERP-access-confirmation timestamps.
The activation-preview endpoint is intentionally omitted from OpenAPI and is
available only when `EMAIL_PROVIDER=mock`; production callers receive no token
or activation URL from an administrative API.

## Google configuration

Create a Google Cloud service account and configure domain-wide delegation for
the Admin SDK Directory scope:

`https://www.googleapis.com/auth/admin.directory.user`

Set:

```dotenv
GOOGLE_DIRECTORY_PROVIDER=google
GOOGLE_DIRECTORY_SERVICE_ACCOUNT_JSON={"type":"service_account",...}
GOOGLE_DIRECTORY_DELEGATED_ADMIN=authorized-admin@your-domain.example
```

Configure the tenant with `--google-domain`, optionally
`--google-customer-id`, and `--google-org-unit` when running
`benson-erp create-admin`. The delegated administrator must be authorized in
Google Admin. Service-account JSON is treated as a secret and must come from a
secret manager in production.

Configure activation delivery with:

```dotenv
EMAIL_PROVIDER=smtp
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_FROM_EMAIL=no-reply@example.com
SMTP_TLS_MODE=starttls
FRONTEND_URL=https://erp.example.com
EMPLOYEE_ACTIVATION_HOURS=24
```

Local Compose and browser acceptance use deterministic `mock` Directory and
email providers. The local-only activation preview endpoint allows an
authorized manager to retrieve the URL that would have been emailed; it is not
available with SMTP. Production startup rejects both mock providers and rejects
non-TLS SMTP or a non-HTTPS frontend URL. `disabled` is fail-closed: the worker
retries and records the provider error instead of falsely marking an identity
created.

Compose explicitly overrides both providers to `mock`; copying `.env.example`
does not enable delivery because its safe default is `EMAIL_PROVIDER=disabled`.
For production, supply SMTP credentials through the deployment secret manager,
not the Compose file or a committed environment file. `SMTP_USERNAME` and
`SMTP_PASSWORD` must either both be set or both be absent. Supported TLS modes
are `starttls` and `ssl` in production; `none` is rejected.

## Recovery and audit

Provider calls use the outbox event ID as the idempotency key. A Google conflict
triggers a lookup of the exact primary email and records that existing subject
ID. Failed jobs retain attempt count, last error, correlation ID, retry time,
and dead-letter state through the common worker infrastructure. Approval and
completion each create tenant-scoped audit records. Activation request rows are
tenant-scoped, FORCE-RLS protected, versioned, and free of the delivery secret
after real SMTP delivery. Used activation records remain as evidence; they are
not overwritten or reused.
