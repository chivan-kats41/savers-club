# Deployment

## What's ready

- `config/settings/production.py`: MySQL (via PyMySQL — see the
  version-spoofing note in that file, fixed for Django 6 compatibility),
  hardened security headers (HSTS, secure cookies, SSL redirect,
  X-Frame-Options, content-type nosniff), SMTP email, Redis cache.
- `requirements.txt`.
- `.env.example` — copy to `.env` and fill in real values. Never commit
  a real `.env`.
- Health endpoints: `/health/`, `/health/live/`, `/health/ready/`
  (the last two check DB connectivity).
- Static/media handled via Django's standard `STATIC_ROOT`/`MEDIA_ROOT`
  — you'll want a real storage backend (S3-compatible, etc.) and a
  reverse proxy or CDN for these in front of Django in production;
  that's not configured here since it's infra-specific.

## Environment variables

See `.env.example` for the full list. Required in production (no safe
default): `SECRET_KEY`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`,
`DB_NAME`/`DB_USER`/`DB_PASSWORD`/`DB_HOST`, `IOTEC_CLIENT_ID`/
`IOTEC_CLIENT_SECRET`/`IOTEC_WALLET_ID`, `IOTEC_CALLBACK_SECRET`.

## Deploy checklist

```bash
export DJANGO_SETTINGS_MODULE=config.settings.production
# ... plus every required env var above ...

pip install -r requirements.txt
python manage.py check --deploy
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py seed_system_settings
python manage.py seed_subscription_plans
python manage.py seed_admin_group
python manage.py createsuperuser
```

Then run the app server (`gunicorn config.wsgi` or similar — not
prescribed here, pick what fits your host), plus separately:

```bash
celery -A config worker -l info
celery -A config beat -l info
```

Both need a reachable `REDIS_URL`. Without them, the app still works —
nothing in the request/response cycle blocks on Celery — but scheduled
reconciliation/expiry jobs won't run, and async notification dispatch
(SMS/email) won't fire. `CELERY_TASK_ALWAYS_EAGER` is only set in the
testing settings, so in production a missing worker means queued tasks
just sit in Redis until one connects.

## Before you point this at real users

1. **Test the ioTec integration live** — see `PAYMENTS.md`. Nothing in
   this codebase has touched ioTec's real servers.
2. **Confirm the disbursement request schema** — the one part of the
   ioTec integration that was inferred rather than documented (see
   `PAYMENTS.md`, "Known gaps").
3. **Add your ioTec Messaging credentials** (SMS is already wired — see the
   "SMS (ioTec Messaging)" section below). Without them OTP codes and SMS
   notifications cannot be delivered.
4. **Run `check --deploy` against your actual production database** —
   this sandbox's checks only verified the DB-connection-independent
   parts; MySQL identifier-length checks need a live connection.
5. **Set a real `IOTEC_CALLBACK_SECRET`** and configure the matching
   header on ioTec's side — the callback endpoints are open to the
   internet otherwise (protected only by that shared secret).
6. Review `SECURITY.md`'s "What's explicitly NOT done yet" list.

## Database backups

Not automated here — standard MySQL backup practice applies
(`mysqldump` on a schedule, or your host's managed-backup feature).
Financial records (`payments.Payment`, `payments.LedgerEntry`,
`payments.Withdrawal`, `subscriptions.SubscriptionPayment`) are the
highest-priority tables to have verified, tested restore procedures
for — test a real restore before you need one.


## SMS (ioTec Messaging)

SMS goes through the ioTec Messaging API (`https://messaging-api.iotec.io`). It is used for
**OTP codes** (registration, password reset) and for **SMS notifications**.

1. Create/sign in to your account at https://messaging.iotec.io, then open
   *Management > Settings > CONFIGURATION* and copy the **Client Id** and generate an **API key**
   (it is shown once). These are *not* your ioTec Pay credentials.
2. Put them in `.env`:
   ```
   IOTEC_MESSAGING_CLIENT_ID=...
   IOTEC_MESSAGING_API_KEY=...
   IOTEC_MESSAGING_PHONE_FORMAT=local      # local | international | plus
   ```
   Production already defaults to `SMS_GATEWAY_CLASS=notifications.services.sms_gateway.IoTecSMSGateway`.
3. Make sure the account has SMS credit and, if ioTec requires it, an approved sender.
4. Verify end to end from the server:
   ```
   python manage.py sms_test +2567XXXXXXXX          # sends a test SMS; fails loudly if rejected
   python manage.py sms_status <id-from-the-log>    # follow up delivery for a message ioTec accepted
   ```
5. `python manage.py check --deploy` warns (`notifications.W001/W002`) if SMS is not configured.

Behaviour: a successful call means ioTec *accepted* the message; handset delivery is asynchronous.
Notification SMS are retried with backoff on timeouts/5xx/429 (Celery); bad credentials are not retried.
Message bodies (including OTPs) and full phone numbers are never written to the logs.
If the recipient format is rejected in your sandbox, change `IOTEC_MESSAGING_PHONE_FORMAT`.
