"""
Base settings shared by every environment.

Environment-specific settings (development/production/testing) import
* from this module and override what they need. Nothing environment-
specific (DEBUG, ALLOWED_HOSTS, DATABASES engine, secure-cookie flags)
belongs in here.
"""
from datetime import timedelta
from pathlib import Path

import environ
import mimetypes

mimetypes.add_type('text/css', '.css', True)
mimetypes.add_type('application/javascript', '.js', True)


# ---------------------------------------------------------------------------
# Paths / env loading
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
# .env is optional in development (dev.py supplies safe fallbacks) but
# required in production. We read it here so every settings module sees it.
env_file = BASE_DIR / ".env"
if env_file.exists():
    environ.Env.read_env(str(env_file))

SECRET_KEY = env("SECRET_KEY", default="dev-secret-key-change-me")

# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "corsheaders",
    "drf_spectacular",
]

LOCAL_APPS = [
    "core",
    "accounts",
    "members",
    "merchants",
    "offers",
    "subscriptions",
    "claims",
    "savings",
    "riders",
    "deliveries",
    "payments",
    "agents",
    "complaints",
    "notifications",
    "item_requests",
    "promotions",
    "hub",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

AUTH_USER_MODEL = "accounts.User"

AUTHENTICATION_BACKENDS = [
    "accounts.authentication.PhoneOrEmailBackend",
    "django.contrib.auth.backends.ModelBackend",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core.middleware.AuditRequestMiddleware",
    "core.twofa.AdminTwoFactorMiddleware",
    "core.csp.CSPMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.csp.csp_nonce",
                "hub.context.unread_notifications",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ---------------------------------------------------------------------------
# Password validation
# ---------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------------------
# i18n / tz
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Africa/Kampala"
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static / media
# ---------------------------------------------------------------------------
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "hub" / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"  # public (offer photos only)
PRIVATE_MEDIA_ROOT = BASE_DIR / "private_media"  # ID documents: served only through permission-checked views
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
FILE_UPLOAD_PERMISSIONS = 0o640

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Auth redirects (server-rendered hub templates)
# ---------------------------------------------------------------------------
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "landing"
LOGOUT_REDIRECT_URL = "landing"

# ---------------------------------------------------------------------------
# DRF
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.ScopedRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "otp_request": "5/hour",
        "otp_verify": "10/hour",
        "login": "10/hour",
        "payment_initiate": "20/hour",
        "payment_callback": "120/min",
        "withdrawal": "10/hour",
        "claim": "30/hour",
        "redeem": "200/hour",
        "delivery_otp": "40/hour",
        "write": "120/hour",
        "agent_action": "300/hour",
        "interact": "600/hour",
        "page_write": "60/hour",
    },
    "EXCEPTION_HANDLER": "core.exceptions.api_exception_handler",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "1K Saver Club API",
    "DESCRIPTION": (
        "Backend API for the 1K Saver Club savings/deals/delivery platform. "
        "Session-authenticated (log in via /accounts/login/ first, then call "
        "these endpoints from the same browser session)."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": "/api/v1",
}

# ---------------------------------------------------------------------------
# Business-rule defaults (overridable at runtime via core.SystemSetting;
# these are only the fallback values used when no DB override exists).
# ---------------------------------------------------------------------------
DEFAULT_SUBSCRIPTION_PRICE_UGX = env.int("DEFAULT_SUBSCRIPTION_PRICE_UGX", default=1000)
DEFAULT_ROUTE_COMMISSION_PERCENT = env("DEFAULT_ROUTE_COMMISSION_PERCENT", default="10.00")
CLAIM_CODE_EXPIRY_HOURS = env.int("CLAIM_CODE_EXPIRY_HOURS", default=48)
DELIVERY_OTP_EXPIRY_MINUTES = env.int("DELIVERY_OTP_EXPIRY_MINUTES", default=30)
DELIVERY_OTP_MAX_ATTEMPTS = env.int("DELIVERY_OTP_MAX_ATTEMPTS", default=5)

# ---------------------------------------------------------------------------
# ioTec Pay (values only — client only ever built in payments app, later phase)
# ---------------------------------------------------------------------------
# The portal calls these "API key" and "secret key"; they are the OAuth2 client id / secret for
# https://id.iotec.io/connect/token. Both naming styles are accepted (IOTEC_API_KEY or IOTEC_CLIENT_ID).
IOTEC_API_KEY = env("IOTEC_API_KEY", default=env("IOTEC_CLIENT_ID", default=""))
IOTEC_SECRET_KEY = env("IOTEC_SECRET_KEY", default=env("IOTEC_CLIENT_SECRET", default=""))
IOTEC_CLIENT_ID = IOTEC_API_KEY          # kept: the payments code and tests read these names
IOTEC_CLIENT_SECRET = IOTEC_SECRET_KEY
IOTEC_WALLET_ID = env("IOTEC_WALLET_ID", default="")
IOTEC_BASE_URL = env("IOTEC_BASE_URL", default="https://pay.iotec.io")
IOTEC_TOKEN_URL = env("IOTEC_TOKEN_URL", default="https://id.iotec.io/connect/token")
IOTEC_CURRENCY = env("IOTEC_CURRENCY", default="UGX")                 # UGX | USD | ITX
# Who pays ioTec's fee: "" = ioTec's default, "ChargeCustomer" = added on top for the payer, "ChargeWallet" = deducted from you.
IOTEC_CHARGES_CATEGORY = env("IOTEC_CHARGES_CATEGORY", default="")
# The URL you register in the ioTec Pay portal (Wallet > Settings > Callback URLs). It is NOT sent in API
# requests (the API has no such field); this setting documents it and powers `manage.py iotec_check`.
IOTECH_CALLBACK_URL = env("IOTECH_CALLBACK_URL", default="")
# Shared secret ioTec sends on every callback (the "Security Header" you configure in the portal).
# Accepted as `X-Callback-Secret: <value>` or `Authorization: Bearer <value>`.
IOTEC_CALLBACK_SECRET = env("IOTEC_CALLBACK_SECRET", default="")
# Public base URL of THIS site, e.g. https://example.com . Used for the card "return" page (ioTec requires https).
SITE_URL = env("SITE_URL", default="").rstrip("/")

PAYMENT_PROVIDERS = {
    "IOTECH_PAY": {
        "PUBLIC_KEY": IOTEC_API_KEY,
        "SECRET_KEY": IOTEC_SECRET_KEY,
        "BASE_URL": IOTEC_BASE_URL,
        "TOKEN_URL": IOTEC_TOKEN_URL,
        "WALLET_ID": IOTEC_WALLET_ID,
        "CURRENCY": IOTEC_CURRENCY,
        "CALLBACK_URL": IOTECH_CALLBACK_URL,
    },
}

# ---------------------------------------------------------------------------
# Celery (configured now, wired up fully in the notifications/payments phases)
# ---------------------------------------------------------------------------
CELERY_BROKER_URL = env("REDIS_URL", default="redis://localhost:6379/0")
CELERY_RESULT_BACKEND = env("REDIS_URL", default="redis://localhost:6379/0")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE

# ioTec Messaging (SMS). Separate credentials from ioTec Pay: get them at https://messaging.iotec.io
# (Management > Settings > CONFIGURATION). Never commit the API key.
IOTEC_MESSAGING_CLIENT_ID = env("IOTEC_MESSAGING_CLIENT_ID", default="")
IOTEC_MESSAGING_API_KEY = env("IOTEC_MESSAGING_API_KEY", default="")
IOTEC_MESSAGING_BASE_URL = env("IOTEC_MESSAGING_BASE_URL", default="https://messaging-api.iotec.io")
IOTEC_MESSAGING_PHONE_FORMAT = env("IOTEC_MESSAGING_PHONE_FORMAT", default="local")  # local | international | plus
IOTEC_MESSAGING_TIMEOUT = env.int("IOTEC_MESSAGING_TIMEOUT", default=10)
SMS_GATEWAY_CLASS = env("SMS_GATEWAY_CLASS", default="notifications.services.sms_gateway.ConsoleSMSGateway")

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{asctime} {levelname} {name} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "verbose"},
        "app_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": LOG_DIR / "application.log",
            "maxBytes": 5 * 1024 * 1024,
            "backupCount": 5,
            "formatter": "verbose",
        },
        "security_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": LOG_DIR / "security.log",
            "maxBytes": 5 * 1024 * 1024,
            "backupCount": 5,
            "formatter": "verbose",
        },
        "payments_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": LOG_DIR / "payments.log",
            "maxBytes": 5 * 1024 * 1024,
            "backupCount": 5,
            "formatter": "verbose",
        },
        "audit_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": LOG_DIR / "audit.log",
            "maxBytes": 5 * 1024 * 1024,
            "backupCount": 5,
            "formatter": "verbose",
        },
    },
    "loggers": {
        "django": {"handlers": ["console", "app_file"], "level": "INFO", "propagate": False},
        "security": {"handlers": ["console", "security_file"], "level": "INFO", "propagate": False},
        "payments": {"handlers": ["console", "payments_file"], "level": "INFO", "propagate": False},
        "audit": {"handlers": ["console", "audit_file"], "level": "INFO", "propagate": False},
    },
}

# ---------------------------------------------------------------------------
# Security headers (safe defaults everywhere; production.py tightens further)
# ---------------------------------------------------------------------------
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False  # JS needs to read this to set X-CSRFToken on fetch()
SESSION_COOKIE_AGE = 60 * 60 * 24 * 14  # 14 days

# --- Admin two-factor ---------------------------------------------------------
ADMIN_REQUIRE_2FA = env.bool("ADMIN_REQUIRE_2FA", default=False)  # forced True in production.py
ADMIN_2FA_MAX_AGE_SECONDS = 12 * 60 * 60
