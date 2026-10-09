from .base import *  # noqa: F401,F403
from .base import BASE_DIR, env

DEBUG = False

ALLOWED_HOSTS = ["*"]

# SQLite by default (zero setup). To develop against MySQL/MariaDB (e.g. XAMPP) set DB_ENGINE=mysql in .env
# plus DB_NAME / DB_USER / DB_PASSWORD / DB_HOST / DB_PORT (see database/README.md).
if env("DB_ENGINE", default="sqlite") == "mysql":
    from ._mysql import mysql_database

    DATABASES = {"default": mysql_database(env)}
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

CORS_ALLOW_ALL_ORIGINS = True
CSRF_TRUSTED_ORIGINS = env.list(
    "CSRF_TRUSTED_ORIGINS", default=["http://localhost:8000", "http://127.0.0.1:8000"]
)

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

# Insecure cookies are fine on plain-http localhost.
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_SSL_REDIRECT = False
