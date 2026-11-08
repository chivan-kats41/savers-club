# Phone-or-email sign-in
Email sign-in works everywhere (including /django-admin/ for long emails), anyone can add an email on the new Account page, emails
are stored lower-case, admin logins now share the lockout rules. See docs/ACCOUNT_AND_PAYOUT_SECURITY.md.

# External-review check
Every claim in an external review was checked against the code with a test (`docs/EXTERNAL_REVIEW_RESPONSE.md`). One was real and is
fixed: a leftover from the legacy renew endpoint could block a real payment for 15 minutes. One nuance is fixed: if the SMS provider
is down, the delivery code now also appears in the customer's account so a delivery can still be confirmed.

# Security batch
Unverified phones can't sign in (verified by tests; admins unchanged), canonical +256 phone numbers (one SIM = one account),
failed-login counters can't be dodged by spelling/case, per-address login ceiling, withdrawal confirmation codes + daily cap,
claim-code guessing guard, `.dockerignore`. See `docs/ACCOUNT_AND_PAYOUT_SECURITY.md`.

# Pending-payment fix
Payments stuck "pending" for days: the member page now asks ioTec by itself (no callback or scheduler needed), parked payments are
re-checked for 14 days so a late approval still activates, the banner stops claiming a phone prompt is waiting after 30 minutes, and
`reconcile_payments` prints what it found. See `docs/PAYMENTS_TROUBLESHOOTING.md`.

# Geo, maps & push update
See `docs/GEO_AND_PUSH.md`. New `geo` app; migrations `core.0005`, `deliveries.0006`, `notifications.0003`, `geo.0001`;
new dependency `pywebpush`. Also fixes a pre-existing crash: `/member/` returned HTTP 500 for any member with a delivery
request (`hub/selectors.py` used `reverse` without importing it).

# Changes after code review

## Money flow
- Payment and withdrawal rows are committed before ioTec is called. A timeout can no longer erase the record of money that may have moved (`IotecUncertainError`); rejected requests are saved `FAILED` and release their reservation; reconciliation closes ones ioTec never received (404 after 10 min).
- Withdrawal amount `NaN`/`Infinity` rejected (was a 500).
- Pending subscription payments that can never finish (no provider payment, >15 min) no longer lock a member out; payments parked for review no longer block a new purchase.

## Plans (new)
- Members choose **Monthly / Quarterly / Yearly** in the pay modal; `plan` accepted on `POST /api/v1/payments/initiate/`.
- `SubscriptionPayment.plan` (migration `subscriptions.0002`); one subscription per member, switching plan stacks time. `seed_subscription_plans` now leaves the Six-Months plan inactive.

## Delivery
- Delivery code is now SMSed to the **customer** at pickup (it was never sent in production).
- Wrong-code attempts are now counted (the counter used to roll back).

## Auth
- Client IP is no longer forgeable: `TRUSTED_PROXY_COUNT` (default 1 in production), nginx overwrites `X-Forwarded-For`, DRF `NUM_PROXIES` set.
- OTPs are 6 digits; max 3 codes per account per hour per purpose.
- Unverified phones cannot log in (admins exempt); numbers held by accounts never verified within 24 h are released. Registration is atomic.
- 2FA gate also covers any `is_staff` user on `/django-admin/`.

## Claims
- Claiming requires an active subscription (`REQUIRE_SUBSCRIPTION_TO_CLAIM`, default on).
- Unknown offer id -> 400; claim codes 6 chars with collision retry; claims that expire during a redeem attempt are restocked.

## Ops
- Swagger/ReDoc/schema only when `ENABLE_API_DOCS` (on in development, off in production).
- Celery broker and cache use separate Redis DBs (`CELERY_BROKER_URL`, `CACHE_URL`).
- nginx: auth rate limit relaxed (30 r/m) for shared carrier-NAT IPs; `http2 on;`.

## Upgrade notes
1. `python manage.py migrate` (adds `subscriptions.0002`, `deliveries.0005`, `payments.0004`, `accounts.0004-0005`); on MySQL-from-SQL installs apply the updated `database/02_schema.sql` change (`plan_id` column).
2. Existing users who never verified their phone must verify (Resend code on the verify page) before logging in.
3. Plan prices are unchanged (1,000 / 3,000 / 10,000). Edit them in the admin console.
4. Set `TRUSTED_PROXY_COUNT=0` if Django is reached with no proxy in front.

## Round 2: the previously open items
- **Delivery fare, online or cash on delivery** (customer's choice per request). Online jobs stay hidden from riders until paid; cash jobs record the cash the rider holds against their balance so it is never paid out twice. Unpaid jobs are cancelled after 30 min, paid-then-failed jobs are flagged `refund_due`. New endpoints: `member/delivery/<id>/pay/` and `/cancel/`. Migrations `deliveries.0005`, `payments.0004`.
- **Referral rewards are now payable**: held `referral.hold_days` (7), then credited and withdrawable via `member/referrals/withdraw/` (same safe withdrawal flow). Member page shows the balance and the minimum.
- **2FA**: secrets encrypted at rest (migration `accounts.0004`/`0005` encrypts existing ones), codes are single-use (replay refused), and enrolling needs the password again. Optional `TOTP_ENCRYPTION_KEY`.
- **PythonAnywhere**: `config.settings.pythonanywhere` (DB cache, inline tasks, no Redis), `manage.py run_periodic` (replaces Celery beat), and `deploy/PYTHONANYWHERE.md`.

## Not changed yet (need a decision)
Automatic refunds for `refund_due` delivery fares (flagged only; refund manually through ioTec for now); an admin screen listing riders who owe commission from cash jobs. `database/02_schema.sql` and `03_reference_data.sql` were updated by hand for the new columns/migrations (the test suite checks they match the models) because no MySQL server was available here: regenerate them on your machine per `database/README.md` if you want them dump-generated.
