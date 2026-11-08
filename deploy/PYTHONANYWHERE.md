# Deploying on PythonAnywhere

PythonAnywhere has no Redis, Docker or Celery worker, so use `config.settings.pythonanywhere` (it builds on production settings).

## 1. Account
* A **paid** account is needed: free accounts can only call a short whitelist of sites, and this app must reach `pay.iotec.io` and `id.iotec.io`.
* Create a MySQL database in the **Databases** tab.

## 2. Code and environment
```bash
cd ~ && unzip savings_hub_django4_fixed.zip && cd savings_hub_django4
mkvirtualenv --python=python3.12 savings_hub
pip install -r requirements.txt
cp .env.example .env     # then edit it (see below)
```
Important `.env` values: `SECRET_KEY` (50+ random chars), `ALLOWED_HOSTS=<you>.pythonanywhere.com`, `CSRF_TRUSTED_ORIGINS=https://<you>.pythonanywhere.com`,
`DB_NAME` (`<you>$savings_hub`), `DB_USER`, `DB_PASSWORD`, `DB_HOST` (`<you>.mysql.pythonanywhere-services.com`), the `IOTEC_*` keys, `TRUSTED_PROXY_COUNT=1`.
Optional: `TOTP_ENCRYPTION_KEY` (see "Two-factor" below).

## 3. Database
```bash
export DJANGO_SETTINGS_MODULE=config.settings.pythonanywhere
python manage.py migrate
python manage.py createcachetable          # the shared cache (rate limits, token cache)
python manage.py seed_system_settings
python manage.py seed_subscription_plans
python manage.py seed_admin_group
python manage.py collectstatic --noinput
python manage.py createsuperuser
```

## 4. Web tab
* WSGI file: set `os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings.pythonanywhere"` and add the project folder to `sys.path`.
* Virtualenv: the one you created. Force HTTPS: on.
* Static files: `/static/` -> `<project>/staticfiles`, `/media/` -> `<project>/media`. **Never map `private_media`** (ID documents).

## 5. Periodic jobs (replaces Celery beat)
Reconciliation, claim/offer/subscription/promotion expiry, unpaid-delivery cancellation and referral credits all run from one command:

* **Always-on task** (best; payments are reconciled every 5 minutes):  
  `/home/<you>/.virtualenvs/savings_hub/bin/python /home/<you>/savings_hub_django4/manage.py run_periodic`
* or an **hourly Scheduled task**:  
  `... manage.py run_periodic --once`

Set `DJANGO_SETTINGS_MODULE=config.settings.pythonanywhere` in the task's environment (or put it in `.env`).

## 6. ioTec callback
Point ioTec's collection / disbursement callbacks at `https://<you>.pythonanywhere.com/api/v1/payments/callback/iotec/collection/` and `.../disbursement/`, and set `IOTEC_CALLBACK_SECRET`.

## 7. Check the client IP
Log in once and look at the newest `login` row in Security Events (admin console): the IP should be *yours*, not PythonAnywhere's. If every visitor shows the same address, set `TRUSTED_PROXY_COUNT=0` in `.env` and reload.

## Two-factor
Admin 2FA secrets are encrypted with a key derived from `SECRET_KEY`. If you ever change `SECRET_KEY`, admins would have to re-enrol, so set `TOTP_ENCRYPTION_KEY` to a fixed random string **before** the first admin enrols and keep it unchanged.
