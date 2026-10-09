"""Shared MySQL/MariaDB wiring so production, development (opt-in) and the MySQL test run all connect the same way."""
SQL_MODE = (
    "STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION"
)


def install_pymysql():
    """Use PyMySQL (pure Python: no C compiler, works on Windows) as the MySQL driver."""
    import pymysql

    pymysql.install_as_MySQLdb()
    # Django 6 checks the mysqlclient version it thinks it's talking to; PyMySQL reports its own, lower
    # number. This is the standard, documented workaround.
    pymysql.version_info = (2, 2, 4, "final", 0)
    pymysql.__version__ = "2.2.4"


def mysql_database(env, default_name="savings_hub", default_user="savings_hub_user", time_zone="Africa/Kampala"):
    """DATABASES['default'] for MySQL 8 / MariaDB from DB_* environment variables."""
    install_pymysql()
    return {
        "ENGINE": "django.db.backends.mysql",
        "NAME": env("DB_NAME", default=default_name),
        "USER": env("DB_USER", default=default_user),
        "PASSWORD": env("DB_PASSWORD", default=""),
        "HOST": env("DB_HOST", default="127.0.0.1"),
        "PORT": env("DB_PORT", default="3306"),
        "CONN_MAX_AGE": env.int("DB_CONN_MAX_AGE", default=60),
        "OPTIONS": {
            "charset": "utf8mb4",
            # Same strict behaviour on MySQL 8, MariaDB and XAMPP (whose default config is lax).
            "init_command": f"SET sql_mode='{SQL_MODE}'",
        },
        # READ COMMITTED: what Django recommends for MySQL. Avoids gap-lock deadlocks around the
        # select_for_update() calls that protect wallets/stock/claim codes.
        "isolation_level": "read committed",
        # Store datetimes in the project's own zone (Africa/Kampala, UTC+3, no daylight saving) instead of UTC.
        # Why: with UTC storage, every "by month / by day / month=..." query makes MySQL run CONVERT_TZ with
        # named zones, which only works if the server's time-zone tables were loaded (they are empty on a fresh
        # MySQL/MariaDB/XAMPP install). Without them the admin dashboards crash and month filters silently
        # return nothing. Matching the DB zone to TIME_ZONE means no conversion is ever needed.
        # Do NOT change TIME_ZONE on a database that already holds data without migrating the stored values.
        "TIME_ZONE": time_zone,
        "TEST": {"CHARSET": "utf8mb4", "COLLATION": "utf8mb4_unicode_ci"},
    }
