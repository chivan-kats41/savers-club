"""Pure geographic maths (no database)."""
import math
from datetime import datetime, timedelta, timezone as tz
import importlib

from django.test import SimpleTestCase, TestCase

from core import geo
from core.geoservice import Point, implausible_jump


class DistanceTests(SimpleTestCase):
    def test_one_degree_of_latitude_is_about_111_km(self):
        self.assertAlmostEqual(geo.haversine_km(10, 30, 11, 30), 111.19, delta=0.2)

    def test_known_ugandan_distance(self):
        # Kampala centre -> Entebbe town: about 32 km as the crow flies
        self.assertAlmostEqual(geo.haversine_km(0.3136, 32.5811, 0.0510, 32.4640), 31.9, delta=0.6)

    def test_symmetric_zero_and_antipodal(self):
        self.assertEqual(geo.haversine_km(1, 2, 1, 2), 0)
        self.assertAlmostEqual(geo.haversine_km(0.3, 32.5, 0.1, 32.1), geo.haversine_km(0.1, 32.1, 0.3, 32.5), places=9)
        self.assertAlmostEqual(geo.haversine_km(0, 0, 0, 180), math.pi * geo.EARTH_RADIUS_KM, delta=0.5)

    def test_bounding_box_contains_every_point_inside_the_radius(self):
        lat, lng, r = 0.3136, 32.5811, 5.0
        lo_lat, hi_lat, lo_lng, hi_lng = geo.bounding_box(lat, lng, r)
        for bearing in range(0, 360, 15):                       # points exactly on the circle
            dlat = math.degrees(r / geo.EARTH_RADIUS_KM) * math.cos(math.radians(bearing))
            dlng = math.degrees(r / geo.EARTH_RADIUS_KM) * math.sin(math.radians(bearing)) / math.cos(math.radians(lat))
            self.assertTrue(lo_lat <= lat + dlat * 0.999 <= hi_lat and lo_lng <= lng + dlng * 0.999 <= hi_lng, bearing)
        self.assertLess(hi_lat - lo_lat, 0.1)                   # and it is genuinely small (cheap query)


class ValidationTests(SimpleTestCase):
    def test_accepts_real_points_including_negative_coordinates(self):
        self.assertEqual(geo.valid_point("0.3136", "32.5811"), (0.3136, 32.5811))
        self.assertEqual(geo.valid_point(-0.6072, 30.6545), (-0.6072, 30.6545))      # Mbarara

    def test_rejects_garbage(self):
        for lat, lng in ((None, 1), ("a", 2), (float("nan"), 1), (1, float("inf")), (91, 10), (-90.1, 10), (10, 181), (0, 0), ("", ""), ([1], 2)):
            with self.assertRaises(ValueError, msg=f"{lat!r},{lng!r}"):
                geo.valid_point(lat, lng)

    def test_rounding_and_formatting(self):
        self.assertEqual(geo.round_coord(0.123456789, 3), 0.123)
        self.assertEqual(geo.format_distance(0.35), "350 m")
        self.assertEqual(geo.format_distance(0.004), "10 m")
        self.assertEqual(geo.format_distance(1.234), "1.2 km")
        self.assertEqual(geo.format_distance(None), "")

    def test_impossible_jump_detection(self):
        now = datetime(2026, 10, 10, 12, 0, tzinfo=tz.utc)
        prev = Point(0.3136, 32.5811, "gps", now - timedelta(minutes=2))
        self.assertTrue(implausible_jump(prev, -0.6072, 30.6545, now))                     # Kampala -> Mbarara in 2 minutes
        self.assertFalse(implausible_jump(prev, 0.3300, 32.6000, now))                     # ordinary movement
        self.assertFalse(implausible_jump(Point(0.3, 32.5, "gps", now - timedelta(hours=5)), -0.6, 30.6, now))   # long ago: fine
        self.assertFalse(implausible_jump(None, 1, 1, now))


class AreaCentroidMigrationTests(TestCase):
    def test_fills_only_empty_known_areas_and_never_overwrites(self):
        from decimal import Decimal
        from django.apps import apps
        from core.models import Area

        mig = importlib.import_module("core.migrations.0005_area_centroids")
        Area.objects.filter(name__in=["Mutungo", "Mbarara"]).delete()
        empty = Area.objects.create(name="Mutungo")
        custom = Area.objects.create(name="Mbarara", latitude=Decimal("-0.5"), longitude=Decimal("30.5"))
        other = Area.objects.create(name="Somewhere Else")
        mig.fill(apps, None)
        for a in (empty, custom, other):
            a.refresh_from_db()
        self.assertIsNotNone(empty.latitude)
        self.assertEqual(custom.latitude, Decimal("-0.500000"))                 # admin's value kept
        self.assertIsNone(other.latitude)                                       # unknown areas untouched
        mig.fill(apps, None)                                                    # idempotent


class SeedGivesAreasPositionsTests(TestCase):
    def test_a_fresh_install_gets_map_positions_when_areas_are_seeded(self):
        """Areas are created by seed_system_settings AFTER migrations run, so the seed must place them too."""
        from django.core.management import call_command
        from core.models import Area

        Area.objects.all().delete()
        call_command("seed_system_settings", verbosity=0)
        self.assertGreaterEqual(Area.objects.count(), 10)
        self.assertEqual(Area.objects.filter(latitude__isnull=True).count(), 0)
        Area.objects.filter(name="Mutungo").update(latitude=1, longitude=2)          # an admin correction survives a re-seed
        call_command("seed_system_settings", verbosity=0)
        self.assertEqual(float(Area.objects.get(name="Mutungo").latitude), 1.0)
