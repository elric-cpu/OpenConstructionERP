# Security configuration

## Required secrets

Production requires unique database credentials, a random application signing secret of at least 32 characters, and a Fernet encryption key. Generate the encryption key with:

```bash
python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

Store secrets in Google Secret Manager or the deployment platform's equivalent. Never commit them or reuse development values. Production startup rejects default credentials, wildcard CORS, the development encryption key, missing encryption material, and malformed Fernet keys.

Employee activation additionally requires `EMAIL_PROVIDER=smtp`, an HTTPS
`FRONTEND_URL`, and SMTP TLS (`starttls` or `ssl`) in production. Mock and
disabled email providers, non-TLS SMTP, and mock Google Directory provisioning
are rejected. Store SMTP credentials and delegated Google service-account JSON
in the deployment secret manager.

## Password and session policy

- Passwords contain at least 12 characters and are hashed with Argon2id.
- Access tokens expire after 15 minutes by default and are tied to a live database session.
- Refresh tokens are opaque, rotated on every use, stored only as SHA-256 hashes, delivered in `HttpOnly`, `SameSite=Strict` cookies, and paired with a separate CSRF secret.
- Session revocation takes effect on the next authenticated API request.
- Users can review and revoke their active devices from **Security → Signed-in devices**.
- Five failed password attempts for the same tenant, email, and address within 15 minutes trigger a temporary login throttle.
- Employee activation tokens are random, tenant-bound, single-use, and
  short-lived (24 hours by default). Only a SHA-256 validation hash is retained;
  the delivery secret is encrypted until delivery and removed after SMTP sends.
  The browser receives the token in a URL fragment, removes it from history,
  and submits it only in the activation request body.

## Multi-factor authentication

Users enroll from **Security → Multi-factor authentication**. The server encrypts TOTP secrets with the configured Fernet key. Enrollment is not active until a valid authenticator code confirms possession.

Ten one-time recovery codes are shown once during enrollment. Users must store them in an approved password manager. Only hashes are retained, and a code is removed atomically after successful use. Help-desk staff must never request an authenticator secret or recovery code by email or chat.

Changing the production encryption key requires a controlled secret-reencryption migration; replacing it without migration makes existing authenticator secrets unreadable.

## Incident response actions

For a suspected account compromise:

1. Suspend or deactivate the user.
2. Revoke all active sessions.
3. Reset credentials through the approved identity workflow.
4. Review `login_events` and `audit_events` for the affected tenant, user, time window, IP addresses, and devices.
5. Rotate integration credentials if the user could access them.
6. Preserve evidence and record the response in the incident log.

MFA and session controls do not replace Google OIDC/Firebase configuration, Cloud Armor, centralized monitoring, or provider-level account protections. Those remain separate production acceptance gates.
