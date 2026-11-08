# Security

This documents what's actually implemented, not a checklist of
intentions. "Defense in depth appropriate for a commercial financial
platform" — never "100% secure."

## Authentication

- Custom `accounts.User` (phone as `USERNAME_FIELD`, email optional),
  UUID primary key.
- `PhoneOrEmailBackend` — login by phone or email, identifier-based
  lockout (5 failures / 15 min) — not IP-based, since Ugandan phone
  numbers commonly share carrier NAT.
- Passwords: Django's built-in hashers, `AUTH_PASSWORD_VALIDATORS`
  enforced (min length 8, common-password check, similarity check,
  numeric-only check).
- OTP (phone verification, password reset, delivery confirmation):
  never stored in plaintext, only a SHA-256 hash; expiry + max-attempts
  enforced per code.
- Session security: `SESSION_COOKIE_HTTPONLY`, `SESSION_COOKIE_SECURE`
  in production, session key rotated on login
  (`request.session.cycle_key()`).

## Authorization

- Role-based: `Role` enum (member/merchant/rider/agent/admin/
  super_admin) on `User`, plus `UserRole` for multi-role assignment and
  explicit role-switching (a user can hold several roles, only one
  active at a time).
- Server-rendered views: `accounts.decorators.role_required(*roles)` /
  `admin_required`.
- API views: `accounts.permissions.IsRole`, `IsAdminRole`,
  `IsOwnerOrAdmin`, `HasCapability`.
- **`is_staff` is never used as a gate for sensitive operations.**
  Granular admin capabilities (`core.AdminCapability` — 12 named
  permissions: `payments_view`, `payments_refund`, `payments_settle`,
  `withdrawals_approve`, `withdrawals_reverse`, `users_suspend`,
  `merchant_verify`, `rider_verify`, `agent_manage`, `fees_manage`,
  `settings_manage`, `reports_view`) back every admin-only endpoint.
  `SUPER_ADMIN` (`is_superuser=True`) bypasses all of these; everyone
  else needs the specific capability, granted via Django Groups or
  direct `user_permissions`. `seed_admin_group` creates a starter
  "Platform Admin" group with a deliberately reduced subset — the most
  sensitive ones (`payments_refund`, `payments_settle`,
  `withdrawals_reverse`, `fees_manage`, `settings_manage`) are excluded
  from the default group and must be granted individually or reserved
  for `SUPER_ADMIN`.

## IDOR protection

Every member/merchant/rider/agent-scoped endpoint resolves "whose data
is this" from `request.user`, never from an ID in the URL or request
body, wherever the design allows it:

- Subscription/savings/claims-list endpoints take no ID at all — "my
  subscription" is always literally the requesting user's.
- Claim redemption takes the claim **code** in the request body (the
  secret the member showed the merchant), never a claim ID in the URL —
  a merchant can never enumerate other merchants' claim IDs.
- A merchant scanning a code that belongs to a different merchant gets
  the exact same generic "Invalid claim code" error as a code that
  doesn't exist at all — never confirms code existence across merchant
  boundaries.
- Delivery job actions verify `job.rider_id == request.user`'s rider
  before allowing any state transition.
- Agent actions (`verify_merchant`, `verify_rider`,
  `resolve_complaint`, `escalate_complaint`) check the target is inside
  the agent's assigned areas before allowing any action.

See `core/tests/test_security_hardening.py::IDORSpotCheckTests` for a
consolidated regression suite, though most of this is also covered
per-app in each app's own test file.

## Rate limiting

- DRF `ScopedRateThrottle` on the API layer: `login` (10/hr),
  `otp_request` (5/hr), `otp_verify` (10/hr), `payment_initiate`
  (20/hr), `payment_callback` (120/min), `withdrawal` (10/hr), `claim`
  (30/hr).
- `core/rate_limit.py` — a cache-based limiter for the server-rendered
  (non-DRF) accounts views: `register`, `password_reset_request`,
  `resend_phone_otp`. These are plain Django views, not DRF `APIView`s,
  so they never got `throttle_classes` automatically and had zero rate
  limiting until this was added.

## CSRF

Django's CSRF middleware is on globally, never disabled. DRF's
`APIView.as_view()` auto-exempts CSRF for its views (standard DRF
behavior, intentional for API endpoints authenticated by session +
explicit `X-CSRFToken` header from the frontend's `fetch()` calls, or by
the shared-secret header for provider callbacks). Verified with an
explicit `Client(enforce_csrf_checks=True)` test against a
session-authenticated POST.

## Audit trail

Two separate append-only logs, by design — different consumers, kept
distinct rather than merged:

- `core.AuditLog` — general cross-domain audit trail (admin actions,
  suspensions, etc.). Django admin enforces read-only (no add/change/
  delete permission on this model).
- `accounts.SecurityEvent` — account-security-specific events (login,
  logout, registration, password reset, phone verification, role
  switch).
- `core.RiskEvent` — fraud/risk signals (login lockout, claim-redemption
  lockout, repeated payment/withdrawal failures). Logged for admin
  review; never auto-blocks a user off a single signal, per design.

## A hard-won lesson from this codebase: audit writes before a raise

`claims.services.redeem_claim`'s lockout path originally wrote a
`RiskEvent` + `ClaimEvent` audit row immediately before raising
`ClaimError` — but the whole function was one `@transaction.atomic`
scope, so raising anything rolled back the entire transaction, silently
discarding the very audit trail meant to survive the failure. This is a
general trap: never write an audit/risk-event row and then raise from
within the same atomic scope that wraps it — the write never actually
persists. The fix pattern used throughout this codebase: do the
state-mutating work inside `with transaction.atomic():`, let that block
exit normally (setting a flag rather than raising inside it), and only
raise — and record anything that must survive regardless of outcome —
after the block has committed. Check any new service function that
logs-then-raises for this pattern.

## File uploads

`merchants.MerchantDocument`, `riders.RiderDocument`,
`offers.OfferImage` validate file extension (whitelist) and max size.
Not yet done: MIME-sniffing / content validation beyond extension,
antivirus scanning, or a fully hardened storage backend (e.g., serving
uploads from a separate domain/bucket with no execute permissions). Fine
for early development; revisit before handling real user uploads at
scale.

## Payment/money-specific hardening

See `PAYMENTS.md` in full. Summary: never trust a frontend-reported
payment/withdrawal status; every financial state transition requires a
verified provider callback or a reconciliation status check; Decimal
everywhere, never float; `select_for_update()` + `transaction.atomic()`
around every stock/balance/redemption mutation (verified with an actual
concurrency test — 5 threads racing for the last unit of stock, exactly
1 succeeds).

## Deploy-time checks

`python manage.py check --deploy` against `config.settings.production`
catches the standard Django production checklist (DEBUG, SECRET_KEY,
HSTS, secure cookies, SSL redirect, etc.) — run it before every
production deploy. Note: full model checks under `--deploy` require a
live database connection (MySQL identifier-length checks query the
connection), so this can't be fully exercised without real production
infrastructure; the connection-independent security checks all pass as
of the last verification.

## What's explicitly NOT done yet

- Two-factor authentication (2FA/TOTP) — mentioned as optional in the
  original spec, not built.
- Full double-entry ledger / settlement batches.
- Live ioTec sandbox testing (see `PAYMENTS.md`).
- MIME-sniffing on file uploads.
- A dedicated `SharedRoute`/`RoutePackage` grouping model for multi-
  parcel delivery trips (simplified to a per-job `delivery_type` field
  — see delivery app notes).


---

## Update: hardening added in this revision
- **Content-Security-Policy** (`core/csp.py`): nonce-based scripts, same-origin only, no `unsafe-eval`. Inline `<script>`/`<style>` tags
  must carry `nonce="{{ csp_nonce }}"`; never add inline `on*=` handlers.
- **Admin two-factor** (`core/twofa.py`, `accounts/totp.py`): enforced in production for `/admin-console/`, `/django-admin/`, `/api/v1/admin/`.
- **Webhooks**: shared-secret header (constant-time), then provider-side status verification; never trust the request body's `status`.
- **Uploads** (`core/uploads.py`): decode + re-encode images, size/pixel limits, private storage for ID documents.
- **Delivery fares** are computed on the server (`delivery.fare_same_area`, `delivery.fare_cross_area`, `delivery.fare_shared_route`).
- **Audit trail**: all admin writes create `AuditLog` rows.
