# GoCity_backend


TO RUN THE CODE 
 .\venv\Scripts\activate
 uvicorn main:app --reload --host 0.0.0.0 --port 8000


New update

## OTP and observability configuration

The backend records request and slow-query latency without logging request
bodies, query parameters, phone numbers, or OTP values. Optional settings:

```env
LOG_LEVEL=INFO
SLOW_REQUEST_MS=500
SLOW_QUERY_MS=150
OTP_TTL_SECONDS=300
OTP_RESEND_COOLDOWN_SECONDS=30
OTP_MAX_VERIFY_ATTEMPTS=5
RIDE_OTP_TTL_SECONDS=600
RIDE_OTP_MAX_VERIFY_ATTEMPTS=5
NOTIFICATION_RETENTION_DAYS=90
RETENTION_SWEEP_INTERVAL_SECONDS=86400
LEGACY_RIDE_OTP_MAX_AGE_MINUTES=15
# Optional dedicated HMAC keys; SECRET_KEY is used until these are configured.
OTP_HASH_SECRET=replace-with-a-distinct-secret
RIDE_OTP_HASH_SECRET=replace-with-a-distinct-secret
```

For production SMS delivery, configure either `TWILIO_ACCOUNT_SID`,
`TWILIO_AUTH_TOKEN`, and `TWILIO_PHONE_NUMBER`, or the existing MSG91
credentials. OTP values are HMAC-protected in memory and ride-start OTPs are
derived from a server secret plus an expiry timestamp, so neither is stored as
plaintext in the database.

For local-only testing without an SMS provider, explicitly configure a master
code; it is disabled in production:

```env
APP_ENV=development
OTP_DEV_MASTER_CODE=choose-a-non-production-code
```

## Admin API access

All `/api/admin/*` endpoints (including driver-document downloads and database
snapshots) fail closed until `ADMIN_API_KEY` is configured. Use a long random
value and set the same value only in the Go-city-admin server environment; do
not expose it through a browser-facing `NEXT_PUBLIC_*` variable.

## Protected FastAPI admin operations

The Go-city-admin UI calls these Python/FastAPI endpoints through its
server-side proxy. They are not browser-public APIs and all require the
`x-admin-api-key` header supplied by that proxy:

- `GET /api/admin/database` — live users, drivers, and bookings snapshot.
- `GET /api/admin/users`, `POST /api/admin/users`, and
  `PATCH /api/admin/users/{user_id}` — customer administration. Customer
  sign-in still requires OTP ownership of the phone number.
- `GET /api/admin/drivers` and `POST /api/admin/drivers` — driver records.
  Creating a driver also creates or promotes the matching phone account to the
  existing `RIDER` role.
- `POST /api/admin/drivers/{driver_id}/verification` — accepts
  `{ "action": "approve" | "reject" }`. Approval is required before a
  driver can go online.
- `PATCH /api/admin/drivers/{driver_id}` — operational status only; it cannot
  bypass the document-verification gate.
