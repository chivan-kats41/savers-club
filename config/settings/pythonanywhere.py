"""Production settings for PythonAnywhere (set DJANGO_SETTINGS_MODULE=config.settings.pythonanywhere in the WSGI file).

PythonAnywhere has no Redis server, no Docker and no long-running Celery worker, so this module takes everything from
production.py and swaps just those three pieces:

* cache  -> a database table (shared by every web worker; create it once with `manage.py createcachetable`)
* Celery -> runs tasks inline in the request (no broker needed). The periodic jobs that Celery beat would run are run by
            `manage.py run_periodic` instead (an Always-on task, or hourly with --once; see deploy/PYTHONANYWHERE.md).
* proxy  -> one trusted proxy (PythonAnywhere's front end) in front of the app.
"""
from .production import *  # noqa: F401,F403
from .production import env

# --- cache: shared across workers, no Redis ------------------------------------------------------------------------------------
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "django_cache_table",
    }
}

# --- Celery: no broker; run tasks inline --------------------------------------------------------------------------------------
CELERY_BROKER_URL = "memory://"
CELERY_RESULT_BACKEND = "cache+memory://"
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = False  # a failing SMS/notification task is logged, never a 500 for the customer

# --- proxy ----------------------------------------------------------------------------------------------------------------------
# PythonAnywhere's load balancer appends the visitor's address to X-Forwarded-For. Confirm on your account (see the doc) and
# set TRUSTED_PROXY_COUNT=0 in .env if the security log ever shows the same IP for every visitor.
TRUSTED_PROXY_COUNT = env.int("TRUSTED_PROXY_COUNT", default=1)
REST_FRAMEWORK = {**REST_FRAMEWORK, "NUM_PROXIES": TRUSTED_PROXY_COUNT}  # noqa: F405

# Offer photos are served by a PythonAnywhere "Static files" mapping (/media/ -> <project>/media). private_media must NEVER be mapped.
