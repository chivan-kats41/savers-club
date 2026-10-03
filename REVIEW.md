# Review: final state

Everything from the first review is now implemented. This file lists what was done and the few things that
cannot be done in code (they need your accounts, servers or a human decision).

## Frontend → database
- All pages render from the database through `hub/selectors.py`; `hub/data.py` is no longer used by any page.
- Per-user pages are scoped from `request.user` (never from the URL).
- Buttons/forms call the real `/api/v1/` endpoints via `hub/static/hub/js/api.js` (CSRF-aware, toasts for errors,
  payment polling, multipart uploads, click tracking). Rider and agent pages auto-refresh every 30 / 60 s.

## Security issues: all fixed
| # | Issue | Fix |
|---|-------|-----|
| 1 | Payment webhooks forgeable when secret empty | Fail-closed + constant-time compare (both webhooks) |
| 2 | Webhook trusted the request body's status | Body is only used to *find* the payment; status is fetched from ioTec's status API. Unreachable provider → left pending for the reconciliation job |
| 3 | Logout via GET | POST only |
| 4 | Default SECRET_KEY could reach production | Production refuses to boot with a short/default key |
| 5 | Client-chosen delivery fare | Server computes fare from `delivery.fare_*` settings; client value ignored |
| 6 | Missing rate limits | Scoped throttles on redeem, delivery OTP, claim cancel, offers, requests, complaints, agent actions, interaction tracking |
| 7 | CDN scripts (unpinned `lucide@latest`, Tailwind play CDN) and no CSP | Tailwind compiled locally; Lucide, Chart.js and Inter font self-hosted & pinned; strict nonce-based CSP (no unsafe-eval, no script CDNs); no inline event handlers |
| 8 | Admin accounts had only a password | TOTP two-factor (RFC 6238, stdlib only) enforced by middleware on the admin console, Django admin and admin API; `reset_2fa` management command for lost devices |
| 9 | Uploads (ID documents) unvalidated and web-reachable | Pillow decode + re-encode (strips EXIF/payloads), size/pixel caps, PDF magic-byte check, random file names, ID documents in **private** storage served only to owner / covering agent / admin |
| 10 | Throttling per-process cache | Production uses Redis cache (already configured) — see Deployment |
| 11 | `.env.example` defaulted to development settings | Defaults to production; dev-only warning |
| 12 | Admin write actions not consistently audited | Every new admin endpoint writes an `AuditLog` row |
| 13 | `db.sqlite3`, `logs/`, `env/` shipped in the zip | Excluded from this package; `.gitignore` added |

## Missing features: all added
Merchant & rider sign-up pages (+ rider document upload, agent can view documents) · offer photos · call/WhatsApp/view tracking ·
notification bell with unread count + inbox + admin broadcast · admin offer approve/reject/pause, merchant/rider verify override ·
editable plans, areas, categories and system settings (capability-gated, audited) · PickupPoint and AgentTask models with admin pages
and agent "my tasks" · ioTec Messaging SMS gateway (OTP + notifications, retries, `sms_test` / `sms_status` commands) · Dockerfile, docker-compose (MySQL, Redis, Celery worker + beat, nginx),
nginx config with TLS + rate limits, WhiteNoise static files, Sentry hook, GitHub Actions CI (migrations check, deploy check, tests, pip-audit).

Tests: 257 passing (`python manage.py test` with `DJANGO_SETTINGS_MODULE=config.settings.testing`).

## What I could not do for you (needs your action)
1. **Rotate secrets.** Your original zip contained `db.sqlite3` with password hashes: change any real passwords/keys that were ever in it.
2. **Real credentials**: ioTec (`IOTEC_*`, `IOTEC_CALLBACK_SECRET`), ioTec Messaging (`IOTEC_MESSAGING_CLIENT_ID` / `IOTEC_MESSAGING_API_KEY`: separate from the Pay credentials), SMTP, `SECRET_KEY`.
   I could not test against the live ioTec or SMS providers; the webhook verification assumes ioTec's status endpoint returns a `status`
   field (as your existing reconciliation code already does). Test with their sandbox before launch.
3. **Hosting**: TLS certificates (`deploy/certs`), DNS, a server, backups of MySQL + `private_media`, uptime monitoring.
4. **ioTec callback allow-list**: if ioTec publishes callback source IPs, add them to nginx (`allow`/`deny`) as a second layer.
5. **Legal/policy**: terms, privacy policy and Uganda data-protection registration (PDPO) for the personal data and ID documents you store.
6. **Browser check**: I verified every page renders, CSP/CSRF/uploads/2FA behaviour and all tests, but I could not open the site in a real browser.
   Click through each role once and check the layout on a phone.

## Known limitations (honest list)
- Not verified against the live ioTec Messaging service (no credentials here). Run `python manage.py sms_test <your number>` first; if the number format is rejected change `IOTEC_MESSAGING_PHONE_FORMAT`.
- The Tailwind CSS is pre-built; if you add new utility classes in templates run `npm install && npm run build:css`.
- `color-mix()` (used only for opacity variants like `bg-muted/40`) needs a reasonably modern browser (Chrome 111+); plain colours work everywhere.
- Admin 2FA has no backup codes (use `reset_2fa` on the server) and no QR code (manual key entry or the otpauth link).
- WebSockets/SSE are not used; "live" pages poll by reloading.


## Update: ioTec Pay (payments) rework
Fixed against the ioTec Pay v1 spec: the mobile-money request was **missing the required `amount`**; disbursement `amount`
was a string and `category` was missing; card payments now send `redirectUrl` + `payerName` and land on a verified return page;
`Cancelled` / `Rejected` / `RolledBack` were ignored (payments stayed pending forever); reconciliation skipped card payments
in `SentToVendor`; a "Success" for the wrong amount could activate a subscription. Added: one callback URL
(`/api/iotec/callback`), `PAYMENT_PROVIDERS` + `IOTEC_API_KEY/IOTEC_SECRET_KEY` names, card/mobile-money switch in the pay forms,
on-demand status verification, `iotec_check`, admin wallet balance. See PAYMENTS.md. Tests: 291 passing.
