"""Things that behave differently on MySQL than on SQLite. These run on whichever database the suite uses,
so run the suite with config.settings.testing_mysql too (see database/README.md)."""
from datetime import datetime, timezone as dt_tz
from decimal import Decimal

from django.db.models import Count
from django.db.models.functions import TruncMonth
from django.test import TestCase
from django.utils import timezone

from accounts.models import Role, User
from core.models import Area
from members.models import Member


class DatabaseTimezoneTests(TestCase):
    def setUp(self):
        self.area = Area.objects.create(name="Tz Town")

    def make_member(self, phone, created):
        u = User.objects.create_user(phone=phone, password="x", role=Role.MEMBER)
        m = Member.objects.create(user=u, area=self.area)
        Member.objects.filter(pk=m.pk).update(created_at=created)
        return m

    def test_month_grouping_and_month_lookup_need_no_server_timezone_tables(self):
        # 23:30 UTC on 31 Jan is 02:30 on 1 Feb in Kampala (UTC+3): it must land in FEBRUARY.
        self.make_member("+256700000011", datetime(2026, 1, 31, 23, 30, tzinfo=dt_tz.utc))
        self.make_member("+256700000012", datetime(2026, 2, 10, 9, 0, tzinfo=dt_tz.utc))
        self.make_member("+256700000013", datetime(2026, 3, 5, 9, 0, tzinfo=dt_tz.utc))
        buckets = {row["m"].month: row["n"] for row in
                   Member.objects.annotate(m=TruncMonth("created_at")).values("m").annotate(n=Count("id"))}
        self.assertEqual(buckets, {2: 2, 3: 1})
        self.assertEqual(Member.objects.filter(created_at__month=2).count(), 2)   # silently 0 on a fresh MySQL before the fix
        self.assertEqual(Member.objects.filter(created_at__year=2026, created_at__month=3).count(), 1)

    def test_naive_datetimes_round_trip_in_kampala_time(self):
        m = self.make_member("+256700000014", datetime(2026, 6, 1, 21, 30, tzinfo=dt_tz.utc))
        m.refresh_from_db()
        self.assertEqual(m.created_at, datetime(2026, 6, 1, 21, 30, tzinfo=dt_tz.utc))   # same instant
        self.assertEqual(timezone.localtime(m.created_at).hour, 0)                        # 00:30 next day, Kampala

    def test_money_columns_keep_two_decimals_exactly(self):
        from subscriptions.models import SubscriptionPlan
        p = SubscriptionPlan.objects.create(code="x", label="X", price=Decimal("1234.50"), period_days=30)
        p.refresh_from_db()
        self.assertEqual(p.price, Decimal("1234.50"))


class ReferenceDataTests(TestCase):
    def test_seed_reference_data_is_idempotent_and_respects_admin_edits(self):
        from django.core.management import call_command
        from offers.models import OfferCategory
        from promotions.models import PromotionPackage

        call_command("seed_reference_data", verbosity=0)
        n_cat, n_pkg = OfferCategory.objects.count(), PromotionPackage.objects.count()
        self.assertGreaterEqual(n_cat, 10)
        self.assertEqual(n_pkg, 3)
        PromotionPackage.objects.filter(code="boost-1d").update(price=Decimal("3500"))
        OfferCategory.objects.filter(key="rice").update(label="Rice & Grains")
        call_command("seed_reference_data", verbosity=0)
        self.assertEqual((OfferCategory.objects.count(), PromotionPackage.objects.count()), (n_cat, n_pkg))
        self.assertEqual(PromotionPackage.objects.get(code="boost-1d").price, Decimal("3500.00"))   # not reset
        self.assertEqual(OfferCategory.objects.get(key="rice").label, "Rice & Grains")
        self.assertTrue(all(p.price >= 500 for p in PromotionPackage.objects.all()))                # ioTec minimum
