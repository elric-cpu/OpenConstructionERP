# Google and Meta integration foundation

These adapters are outbox-facing seams only. They are disabled and dry-run by default,
make no calls during application startup, and intentionally do not add API routes or
storage tables. A durable caller should store one command per provider using
`DeliveryCommand.idempotency_key`, then mark it delivered only after an accepted result.

## Authentication boundaries

- Google Ads supports ADC or a service account key. The service-account email must be
  explicitly granted access in Google Ads; OAuth alone is insufficient. Ads also needs a
  developer token. New offline-conversion users must evaluate the Data Manager API because
  Google warns that `UploadClickConversion` eligibility changed June 15, 2026.
- Google Business Profile Local Posts require a business owner/manager's OAuth grant with
  `https://www.googleapis.com/auth/business.manage`. Service-account credentials and ADC
  are deliberately not accepted by the GBP adapter. Store refresh credentials in Secret
  Manager and expose only a short-lived access token to the adapter when the OAuth flow is
  implemented.
- Meta Conversions API uses a Pixel/Dataset access token. Store it in Secret Manager and
  rotate it according to Meta Business controls.

## Environment variables

Every integration requires both `*_ENABLED=true` and `*_LIVE=true` before it can send.
With only `*_ENABLED`, adapters validate/build commands but return dry-run results.

Google credential selection is `BENSON_GOOGLE_SERVICE_ACCOUNT_JSON`, then
`BENSON_GOOGLE_SERVICE_ACCOUNT_FILE`, then ADC. Google Ads additionally uses
`BENSON_GOOGLE_ADS_CUSTOMER_ID`, `BENSON_GOOGLE_ADS_LOGIN_CUSTOMER_ID` (optional),
`BENSON_GOOGLE_ADS_DEVELOPER_TOKEN`, and `BENSON_GOOGLE_ADS_CONVERSION_ACTION`.

GBP uses `BENSON_GBP_ACCOUNT_ID`, `BENSON_GBP_LOCATION_ID`, and a short-lived
`BENSON_GBP_USER_OAUTH_ACCESS_TOKEN`. Meta uses `BENSON_META_PIXEL_ID` and
`BENSON_META_ACCESS_TOKEN`.

## Privacy and delivery rules

- Advertising payloads fail closed unless ad-user-data consent is explicitly `GRANTED`.
- Email, phone, name, and address match fields are normalized and SHA-256 hashed. Raw lead
  notes, project scope, attachments, IP addresses, and internal IDs are never included.
- Google receives at most hashed email/phone plus a click ID; Meta receives hashed matching
  fields, browser/click IDs when present, and a hashed external ID.
- Stable event IDs provide Google `orderId`, Meta `event_id`, and the local outbox key.
- Transport uses bounded timeouts and retries only transient HTTP failures. Provider
  partial failures still require caller-side inspection and durable retry state.

## Primary documentation reviewed July 16, 2026

- Google Business Profile OAuth: https://developers.google.com/my-business/content/implement-oauth
- Local Posts create method: https://developers.google.com/my-business/reference/rest/v4/accounts.locations.localPosts/create
- Google Ads service accounts: https://developers.google.com/google-ads/api/docs/oauth/service-accounts
- Offline conversions and normalization: https://developers.google.com/google-ads/api/docs/conversions/upload-offline
- Data Manager access: https://developers.google.com/data-manager/api/devguides/quickstart/set-up-access
- google-auth ADC: https://google-auth.readthedocs.io/en/stable/reference/google.auth.html
- Meta CAPI parameters: https://developers.facebook.com/docs/marketing-api/conversions-api/parameters
- Meta CAPI best practices: https://developers.facebook.com/docs/marketing-api/conversions-api/best-practices

No provider offers a safe substitute for account approval, customer-data terms, consent,
access grants, or live sandbox validation. Keep `*_LIVE` false until those gates and a
durable integration outbox are complete.
