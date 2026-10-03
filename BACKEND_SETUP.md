# Backend Setup

This is the Django backend for **1K Saver Club / Savings Hub**. This
document gets a fresh clone running locally. For production, see
`DEPLOYMENT.md`. For the payment integration, see `PAYMENTS.md`. For
security posture, see `SECURITY.md`. For the API surface, see `API.md`.

## Requirements

- Python 3.12+ (the reference environment used 3.12.3; the original
  Windows dev machine's `env/` used Python 3.14 — either works)
- SQLite (bundled with Python) for local development
- MySQL 8+ for production (see `config/settings/production.py`)
- Redis, for caching and Celery, in production (optional locally —
  development/testing settings use in-process locmem cache and Celery's
  eager-execution mode instead)

## First-time setup

```bash
python -m venv env
source env/bin/activate          # Windows: env\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env — at minimum set SECRET_KEY to something random for local
# dev. Everything else has a working default for local development.

python manage.py migrate
python manage.py seed_system_settings
python manage.py seed_subscription_plans
python manage.py seed_admin_group
python manage.py seed_demo_data      # optional — populates dev data from
                                       # hub/data.py; all demo accounts
                                       # get the password DemoPass123!
python manage.py createsuperuser      # your own admin login
python manage.py runserver
```

Visit `http://localhost:8000/` for the site, `http://localhost:8000/django-admin/`
for the Django admin, `http://localhost:8000/api/docs/` for the interactive
API docs (Swagger UI).

## Settings layout

`config/settings/` is split by environment:

- `base.py` — everything shared. Installed apps, middleware, REST
  framework config, logging, business-rule defaults, Celery config.
- `development.py` — SQLite, `DEBUG=True`, permissive `ALLOWED_HOSTS`,
  console email backend, locmem cache.
- `production.py` — MySQL (via PyMySQL — see the note in that file about
  its version-spoofing quirk with Django 6), hardened security headers,
  Redis cache, SMTP email.
- `testing.py` — in-memory SQLite, fast password hasher, eager Celery
  task execution (no broker needed to run the test suite), locmem cache.

`manage.py` defaults to `config.settings.development`. `config/wsgi.py`
and `config/asgi.py` default to `config.settings.production` — override
`DJANGO_SETTINGS_MODULE` explicitly wherever that's wrong for your
deployment.

## Environment variables

See `.env.example` for the full list with defaults. The important ones
for local dev are just `SECRET_KEY`; everything else works out of the
box against SQLite. For payments, you'll need real ioTec credentials —
see `PAYMENTS.md`.

## Running the test suite

```bash
DJANGO_SETTINGS_MODULE=config.settings.testing python manage.py test
```

143+ tests as of the last phase built (accounts/RBAC, every domain
app's models and services, concurrency tests, payment/withdrawal flows
with mocked ioTec calls, security hardening). Run with `--shuffle` or
`--reverse` periodically to catch order-dependent test bugs — this
caught a real cache-isolation issue during development (see git history
/ project memory for that story if you're curious).

## Background jobs (Celery)

Business-critical scheduled work — payment/withdrawal reconciliation,
expiring stale claims/offers/subscriptions — runs via Celery. Locally
you don't need this running for the app to function (nothing blocks on
it), but scheduled jobs won't fire without it:

```bash
# Terminal 1 — worker
celery -A config worker -l info

# Terminal 2 — beat (the scheduler)
celery -A config beat -l info
```

Both need Redis running (`redis-server`) and `REDIS_URL` pointed at it.
The full schedule is in `config/celery.py`. Every scheduled job also has
a plain management command you can run manually without Celery at all:
`reconcile_payments`, `expire_claims`, `expire_offers`,
`expire_subscriptions`.

## Seed / management commands reference

| Command | What it does |
|---|---|
| `seed_system_settings` | Business-rule defaults (subscription price, commission %, OTP/claim expiry, withdrawal limits) into `core.SystemSetting`, admin-editable from there on |
| `seed_subscription_plans` | The 4 plans from `hub/data.py`'s `SUBSCRIPTION_PLANS` |
| `seed_admin_group` | Creates the "Platform Admin" `Group` with a starter capability set, assigns existing `role=admin` users to it |
| `seed_demo_data` | Dev-only — imports `hub/data.py`'s sample members/merchants/offers as real DB rows |
| `expire_claims` / `expire_offers` / `expire_subscriptions` | Manual/cron-runnable equivalents of the scheduled Celery tasks |
| `reconcile_payments` | Polls ioTec for stuck `PENDING` payments/withdrawals |
| `simulate_payment_success <external_reference> [--fail]` | **DEV ONLY**, refuses to run outside `DEBUG=True` — manually drives a pending subscription payment to success/failure, standing in for a real ioTec callback |

## Project layout

One Django app per domain, per the original phased build plan:
`core` (cross-cutting: settings, audit log, risk events, health checks),
`accounts` (auth/RBAC), `members`, `merchants`, `offers`, `subscriptions`,
`claims`, `savings`, `riders`, `deliveries`, `payments`, `agents`,
`complaints`, `notifications`, plus `hub` (the original frontend
prototype — templates/static/nav).

**Important**: `hub/views.py` still renders from `hub/data.py`'s
hardcoded sample lists, not the real domain models above. The backend
(models, business logic, API endpoints, tests) is fully built and
functional independently — but the actual frontend pages you see when
browsing the site are still showing the original static prototype data,
not live database content. Wiring `hub/views.py` to real querysets is
intentionally a later step (it needs every domain to exist first, which
they now do) and hasn't been done yet.
