# Database: 1K Saver Club (MySQL)

A standard MySQL schema for the whole platform: **63 InnoDB tables, 104 foreign keys, 131 secondary indexes, utf8mb4**.
The SQL files here are generated from the Django models by migrating a real MySQL server, and tests fail if they ever
drift from the code (`hub/tests/test_schema_sql.py`).

| File | What it is |
|---|---|
| `01_create_database.sql` | Creates the `savings_hub` database and a least-privilege app user. **Edit the password first.** |
| `02_schema.sql` | All 63 tables, keys and indexes (`CREATE TABLE IF NOT EXISTS`, safe to re-run). |
| `03_reference_data.sql` | 13 areas, 14 system settings, 4 plans, 15 offer categories, 3 promotion packages, and Django's migration records. No users or personal data. Safe to re-run. |
| `DATA_DICTIONARY.md` | Every table and column, grouped by feature, with foreign keys. |
| `mysql-recommended.cnf` | Server settings for a production box. |
| `backup_mysql.sh` / `backup_mysql.bat` | Nightly compressed backup with retention (Linux / Windows). |

## 1. Version requirement (read this first)

**Django 6.1 refuses to start on MySQL older than 8.4 or MariaDB older than 10.11.** Check yours:

```
mysql -u root -p -e "SELECT VERSION();"
```

- Docker: `docker-compose.yml` already uses `mysql:8.4`. 
- Windows: use the MySQL Installer (8.4 LTS), or confirm your XAMPP's MariaDB is 10.11+. Older XAMPP builds ship MariaDB 10.4, which Django 6.1 rejects with `NotSupportedError`.
- Ubuntu 24.04's `apt` MySQL is 8.0: too old; use the MySQL APT repository or Docker.

## 2. Create the database

Edit the password in `01_create_database.sql` (replace `CHANGE_ME_TO_A_LONG_RANDOM_PASSWORD`), then:

```
mysql -u root -p < database/01_create_database.sql
```

Use `'%'` instead of `'localhost'` in that file only if the app connects from another machine/container.
On a production server delete the last `GRANT` (the `test_savings_hub` line); it exists only so developers can run the test suite.

## 3. Put the settings in `.env`

```
DB_NAME=savings_hub
DB_USER=savings_hub_user
DB_PASSWORD=the-password-you-chose
DB_HOST=127.0.0.1
DB_PORT=3306
# Development only: use MySQL instead of SQLite
DB_ENGINE=mysql
DJANGO_SETTINGS_MODULE=config.settings.development     # production: config.settings.production
```

## 4. Build the tables: pick ONE path

**Path A (recommended): let Django build it.** Always correct, always current:
```
python manage.py migrate
python manage.py seed_system_settings
python manage.py seed_subscription_plans
python manage.py seed_reference_data        # categories + promotion packages (idempotent)
python manage.py seed_admin_group
python manage.py createsuperuser           # also creates the admin's member/merchant/rider/agent profiles
```

**Path B: load the SQL files** (e.g. a DBA prefers reviewing SQL, or no Python on the DB host):
```
mysql -u savings_hub_user -p savings_hub < database/02_schema.sql
mysql -u savings_hub_user -p savings_hub < database/03_reference_data.sql
python manage.py migrate                    # prints "No migrations to apply" and creates Django's permission rows
python manage.py seed_admin_group
python manage.py createsuperuser
```
Path B was verified: loading the files into a fresh database gives a schema byte-for-byte equivalent (every column, index,
foreign key, engine and collation) to the one `migrate` builds, and Django reports `No migrations to apply`.

Check it: `python manage.py iotec_check` (payments) and `python manage.py check`.

## 5. Design decisions (and why)

- **InnoDB + utf8mb4 / `utf8mb4_unicode_ci`**: transactions and row locks (wallets, stock, claim codes use `SELECT ... FOR UPDATE`),
  full Unicode incl. emoji. `unicode_ci` rather than MySQL-8-only `0900_ai_ci` so MariaDB works too.
- **Strict SQL mode** is set on every connection (`STRICT_TRANS_TABLES`, ...), so bad data errors instead of being silently truncated,
  even on lax servers like a default XAMPP.
- **READ COMMITTED isolation** (what Django recommends for MySQL): avoids gap-lock deadlocks around `select_for_update()`.
- **Time zones**: datetimes are stored in **Africa/Kampala local time** (UTC+3, no daylight saving), not UTC. Reason: with UTC storage MySQL
  must convert zones for every "by month / by day" query, which only works if the server's time-zone tables are loaded; they are empty on a
  fresh install, so dashboards crashed and month filters silently returned nothing (found by running the test suite on real MySQL). If you
  ever change `TIME_ZONE`, migrate the stored values first.
- **Money** is `decimal(12,2)` in UGX (never float). UUIDs are `char(32)`.
- **Uploaded files are not in the database.** Offer photos live in `media/`, rider ID documents in `private_media/`. Back those up too.

## 6. Security

- The app user can only touch `savings_hub`. No `FILE`, `SUPER`, `PROCESS` or `GRANT`.
- Bind MySQL to `127.0.0.1` (or a private network) and firewall port 3306. Never expose it to the internet.
- For stricter separation use two users: a migration user (DDL) and an app user with only `SELECT, INSERT, UPDATE, DELETE`
  (+ `LOCK TABLES`) for day-to-day; run `migrate` as the first.
- Passwords, ID-document paths, TOTP secrets and callback payloads are stored; encrypt disks/backups and restrict who can read them.

## 7. Backups

```
./database/backup_mysql.sh          # Linux: add to cron, e.g.  15 2 * * *
database\backup_mysql.bat           # Windows: run from Task Scheduler
```
Restore: `gunzip -c backup.sql.gz | mysql -u savings_hub_user -p savings_hub`. Test a restore regularly: an untested backup is a hope, not a backup.

## 8. Regenerating the SQL files (after changing a model)

```
python manage.py makemigrations && python manage.py migrate        # on a scratch MySQL database
mysqldump --no-data --skip-comments --skip-add-drop-table --no-tablespaces --set-gtid-purged=OFF savings_hub > raw.sql
```
Then strip `AUTO_INCREMENT=n`, change `CREATE TABLE` to `CREATE TABLE IF NOT EXISTS`, keep the header comment, and refresh
`03_reference_data.sql` the same way (`--no-create-info --complete-insert --insert-ignore --skip-extended-insert`, tables
`django_migrations core_area core_systemsetting subscriptions_subscriptionplan offers_offercategory promotions_promotionpackage`).
`hub/tests/test_schema_sql.py` tells you when this is needed. Path A never needs it.

## 9. What was and wasn't tested
Tested on **MySQL 8.0.46** (Linux): all 63 tables build, the whole test suite (314 tests) passes, and the SQL files load and match.
Django 6.1's minimum-version check was bypassed for that run (`ALLOW_UNSUPPORTED_DB_VERSION=1` in `config/settings/testing_mysql.py`,
lab use only) because 8.4 wasn't installable there. **Not tested on MySQL 8.4 or MariaDB**; the SQL uses nothing beyond 8.0/MariaDB 10.5
features, but run `DJANGO_SETTINGS_MODULE=config.settings.testing_mysql python manage.py test` on your target server once.
