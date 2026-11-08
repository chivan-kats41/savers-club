"""Run the whole test suite against a REAL MySQL/MariaDB (what production uses) instead of SQLite:

    DB_PASSWORD=... DJANGO_SETTINGS_MODULE=config.settings.testing_mysql python manage.py test

Needs the user from database/01_create_database.sql (it may create/drop `test_savings_hub`).
"""
from .base import env
from .testing import *  # noqa: F401,F403
from ._mysql import mysql_database

DATABASES = {"default": mysql_database(env)}
DATABASES["default"]["CONN_MAX_AGE"] = 0

# Django 6.1 requires MySQL >= 8.4 (MariaDB >= 10.11). To exercise an older server in a lab/CI box only, set
# ALLOW_UNSUPPORTED_DB_VERSION=1. Never do this in production.
if env.bool("ALLOW_UNSUPPORTED_DB_VERSION", default=False):
    from django.db.backends.mysql.base import DatabaseWrapper

    DatabaseWrapper.check_database_version_supported = lambda self: None
