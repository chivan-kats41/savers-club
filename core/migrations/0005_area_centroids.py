from django.db import migrations

from core.area_centroids import fill_empty_positions


def fill(apps, schema_editor):
    fill_empty_positions(apps.get_model("core", "Area"))


class Migration(migrations.Migration):
    dependencies = [("core", "0004_alter_admincapability_options")]
    operations = [migrations.RunPython(fill, migrations.RunPython.noop)]
