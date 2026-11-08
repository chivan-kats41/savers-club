"""Give the launch areas approximate centre points so distance / "near me" features work out of the box.

These are APPROXIMATE centroids (good to roughly 1 km) entered from general knowledge, not surveyed data. Only areas
whose coordinates are still empty are touched, and an admin can correct any of them afterwards. Please check them on a
map before launch (Admin console > Areas) - Kireka, Mutungo and Kitintale sit close together, so a wrong pin matters.
"""
from django.db import migrations

APPROX_CENTRES = {
    "Mutungo": (0.3170, 32.6370),
    "Kitintale": (0.3260, 32.6420),
    "Luzira": (0.2985, 32.6350),
    "Kireka": (0.3464, 32.6475),
    "Bweyogerere": (0.3614, 32.6556),
    "Makindye": (0.2850, 32.5900),
    "Nansana": (0.3640, 32.5280),
    "Nakawa": (0.3317, 32.6148),
    "Ntinda": (0.3528, 32.6111),
    "Katabi": (0.0910, 32.4650),
    "Entebbe": (0.0512, 32.4637),
    "Kampala": (0.3476, 32.5825),
    "Wakiso": (0.4044, 32.4594),
}


def fill_centres(apps, schema_editor):
    Area = apps.get_model("core", "Area")
    for name, (lat, lng) in APPROX_CENTRES.items():
        Area.objects.filter(name=name, latitude__isnull=True, longitude__isnull=True).update(latitude=lat, longitude=lng)


class Migration(migrations.Migration):
    dependencies = [("core", "0004_alter_admincapability_options")]
    operations = [migrations.RunPython(fill_centres, migrations.RunPython.noop)]
