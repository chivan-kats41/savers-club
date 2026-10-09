from .base import *  # noqa: F401,F403
from .base import env

DEBUG = False

from django.core.exceptions import ImproperlyConfigured  # noqa: E402

if SECRET_KEY.startswith("dev-secret-key") or len(SECRET_KEY) < 40:  # noqa: F405
    raise ImproperlyConfigured("Set a long random SECRET_KEY in the environment for production.")

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

# ---------------------------------------------------------------------------
# Database — MySQL via PyMySQL (pure-python, avoids native mysqlclient build
# deps on Windows dev machines / constrained hosts). Swap for mysqlclient in
# production if you prefer the C driver; PyMySQL is drop-in DB-API compatible.
# ---------------------------------------------------------------------------
from ._mysql import mysql_database  # noqa: E402

DATABASES = {"default": mysql_database(env, default_name="", default_user="")}
DATABASES["default"]["NAME"] = env("DB_NAME")        # required in production: fail loudly if missing
DATABASES["default"]["USER"] = env("DB_USER")
DATABASES["default"]["PASSWORD"] = env("DB_PASSWORD")
DATABASES["default"]["HOST"] = env("DB_HOST", default="localhost")

CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": env("REDIS_URL", default="redis://localhost:6379/1"),
    }
}

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = env("EMAIL_HOST", default="")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default=EMAIL_HOST_USER)

# ---------------------------------------------------------------------------
# Hardened security — only enforced once real HTTPS is in front of this.
# ---------------------------------------------------------------------------
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Admin accounts must always use two-factor in production.
ADMIN_REQUIRE_2FA = True

# ---------------------------------------------------------------------------
# Static files: served by WhiteNoise (compressed + hashed names). Offer photos
# (MEDIA_ROOT) are served by nginx; ID documents (PRIVATE_MEDIA_ROOT) are NEVER
# exposed by nginx — only through the permission-checked Django view.
# ---------------------------------------------------------------------------
_mw = list(MIDDLEWARE)  # noqa: F405
_mw.insert(_mw.index("django.middleware.security.SecurityMiddleware") + 1, "whitenoise.middleware.WhiteNoiseMiddleware")
MIDDLEWARE = _mw
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SESSION_COOKIE_AGE = 60 * 60 * 24 * 14

# Errors/perf to Sentry when SENTRY_DSN is set (no PII).
_dsn = env("SENTRY_DSN", default="")
if _dsn:
    import sentry_sdk

    sentry_sdk.init(dsn=_dsn, send_default_pii=False, traces_sample_rate=env.float("SENTRY_TRACES_RATE", default=0.05),
                    environment=env("SENTRY_ENV", default="production"))

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", default="INFO")},
}

# SMS goes through ioTec Messaging in production (override with SMS_GATEWAY_CLASS only for testing).
SMS_GATEWAY_CLASS = env("SMS_GATEWAY_CLASS", default="notifications.services.sms_gateway.IoTecSMSGateway")
