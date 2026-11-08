"""database/02_schema.sql and 03_reference_data.sql are generated artefacts. This fails (on any database) the moment a
model or migration changes without regenerating them, so the shipped SQL can never silently drift from the code."""
import re
from pathlib import Path

from django.apps import apps
from django.db.migrations.loader import MigrationLoader
from django.db import connection
from django.test import SimpleTestCase

DB_DIR = Path(__file__).resolve().parents[2] / "database"
REGEN = "Regenerate the SQL files (see database/README.md, section 'Regenerating')."


def parse_schema():
    sql = (DB_DIR / "02_schema.sql").read_text(encoding="utf-8")
    tables = {}
    for m in re.finditer(r"CREATE TABLE IF NOT EXISTS `(\w+)` \((.*?)\n\) ENGINE", sql, re.S):
        tables[m.group(1)] = set(re.findall(r"^  `(\w+)` ", m.group(2), re.M))
    return tables


class SchemaFileInSyncTests(SimpleTestCase):
    def test_every_model_table_and_column_is_in_02_schema_sql(self):
        sql_tables = parse_schema()
        sql_tables.pop("django_migrations")     # created by Django itself, not by a model
        model_tables = {}
        for model in apps.get_models(include_auto_created=True):
            if model._meta.proxy or not model._meta.managed:
                continue
            model_tables[model._meta.db_table] = {f.column for f in model._meta.local_concrete_fields}
        self.assertEqual(set(sql_tables), set(model_tables), "Tables differ. " + REGEN)
        for table, cols in model_tables.items():
            self.assertEqual(sql_tables[table], cols, f"Columns of {table} differ. " + REGEN)

    def test_every_migration_is_registered_in_03_reference_data_sql(self):
        loader = MigrationLoader(None, ignore_no_migrations=True)
        on_disk = {(app, name) for (app, name) in loader.disk_migrations}
        text = (DB_DIR / "03_reference_data.sql").read_text(encoding="utf-8")
        registered = set(re.findall(r"VALUES \(\d+,'(\w+)','(\w+)'", text))
        self.assertEqual(on_disk, registered, "django_migrations rows differ. " + REGEN)

    def test_sql_files_contain_no_personal_or_secret_data(self):
        for name in ("01_create_database.sql", "02_schema.sql", "03_reference_data.sql"):
            text = (DB_DIR / name).read_text(encoding="utf-8")
            self.assertNotRegex(text, r"pbkdf2_|sha256\$|\+2567\d{8}|@\w+\.\w+")
        self.assertIn("CHANGE_ME", (DB_DIR / "01_create_database.sql").read_text(encoding="utf-8"))
