from .base import *  # noqa: F401,F403

DEBUG = False
ALLOWED_HOSTS = ["testserver"]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]  # fast tests

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_SSL_REDIRECT = False

# Off by default in tests so existing fixtures/counts are unaffected; the feature has its own tests that turn it on.
AUTO_CREATE_ADMIN_PROFILES = False

# Existing fixtures claim offers without buying a plan; the subscription gate has its own tests that turn it on.
REQUIRE_SUBSCRIPTION_TO_CLAIM = False


# Geo tests must never reach the network: geocoder/router off (the code falls back to local data / estimates).
GEOCODER_BASE_URL = ""
OSRM_BASE_URL = ""
