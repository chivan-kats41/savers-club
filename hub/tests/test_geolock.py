"""Geo-locking end to end: members only see/claim nearby offers, riders only see/accept nearby jobs, merchants must be
on the map, location data is validated and private. Geo enforcement is switched ON for every test here."""
import json
from datetime import timedelta
from decimal import Decimal

from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import Role, User
from claims.models import OfferClaim
from claims.services import ClaimError, claim_offer
from core import geoservice
from core.models import Area, AuditLog, SystemSetting
from deliveries.models import DeliveryJob
from deliveries.services import DeliveryError, accept_job
from members.models import Member
from merchants.models import Merchant
from offers.models import Offer, OfferCategory
from offers.merchant_services import OfferError, create_offer
from riders.models import Rider
from subscriptions.models import Subscription, SubscriptionPlan

# Kampala (Mutungo-ish). Offsets: 0.01 deg latitude ~ 1.11 km
HOME = (0.3290, 32.6490)


def at(km_north):
    return (HOME[0] + km_north / 111.19, HOME[1])


def post(client, url, data=None):
    return client.post(url, json.dumps(data or {}), content_type="application/json")


@override_settings(GEO_ENFORCE_DEFAULT=True)
class GeoBase(TestCase):
    def setUp(self):
        cache.clear()
        self.home_area = Area.objects.create(name="Mutungo Test", latitude=Decimal("0.329"), longitude=Decimal("32.649"))
        self.far_area = Area.objects.create(name="Mbarara Test", latitude=Decimal("-0.6072"), longitude=Decimal("30.6545"))
        self.unmapped_area = Area.objects.create(name="Unmapped")
        self.cat = OfferCategory.objects.create(key="general", label="General")
        self.member_user = User.objects.create_user(phone="+256770100001", password="x", role=Role.MEMBER, first_name="Mem")
        self.member = Member.objects.create(user=self.member_user, area=self.home_area)
        plan = SubscriptionPlan.objects.create(code="m", label="M", price=1000, period_days=30)
        Subscription.objects.create(member=self.member, plan=plan, status=Subscription.Status.ACTIVE,
                                    current_period_start=timezone.now(), current_period_end=timezone.now() + timedelta(days=20))
        self.near = self.shop("Near Shop", at(0.2), self.home_area)           # ~200 m
        self.mid = self.shop("Mid Shop", at(3.0), self.home_area)             # ~3 km
        self.far = self.shop("Far Shop", at(12.0), self.home_area)            # ~12 km
        self.mbarara = self.shop("Mbarara Shop", (-0.6072, 30.6545), self.far_area)   # ~270 km
        self.ghost = self.shop("Unmapped Shop", None, self.unmapped_area)     # nowhere on the map
        self.offers = {m.business_name: self.offer(m) for m in (self.near, self.mid, self.far, self.mbarara, self.ghost)}

    def shop(self, name, point, area):
        u = User.objects.create_user(phone=f"+2567701{abs(hash(name)) % 90000 + 10000}", password="x", role=Role.MERCHANT)
        kw = {"latitude": Decimal(str(round(point[0], 6))), "longitude": Decimal(str(round(point[1], 6))), "location_source": "gps"} if point else {}
        return Merchant.objects.create(user=u, business_name=name, category=self.cat, area=area, status=Merchant.Status.VERIFIED, **kw)

    def offer(self, merchant, **kw):
        return Offer.objects.create(merchant=merchant, category=self.cat, area=merchant.area, item_name=f"Rice {merchant.business_name}",
                                    normal_price=20000, member_price=18000, quantity=5, status=Offer.Status.ACTIVE,
                                    expires_at=timezone.now() + timedelta(days=2), **kw)

    def member_at(self, point, source="gps", age_min=0):
        self.member.latitude, self.member.longitude = Decimal(str(round(point[0], 3))), Decimal(str(round(point[1], 3)))
        self.member.location_source = source
        self.member.location_updated_at = timezone.now() - timedelta(minutes=age_min)
        self.member.save()

    def visible_names(self, ctx_key="results", **params):
        c = Client(); c.force_login(self.member_user)
        r = c.get(reverse("member"), {"q": "Rice", **params})
        self.assertEqual(r.status_code, 200)
        return [card["seller"] for card in r.context[ctx_key]], r


class MemberVisibilityTests(GeoBase):
    def test_no_location_means_nothing_is_shown_and_a_gate_asks_for_it(self):
        names, r = self.visible_names()
        self.assertEqual(names, [])
        self.assertTrue(r.context["geo"]["locked"])
        self.assertContains(r, "Share your location to see deals near you")
        self.assertEqual(r.context["nearby_deals"], [])
        self.assertEqual(r.context["basket_items"], [])

    def test_only_offers_within_the_radius_are_visible_nearest_first(self):
        self.member_at(HOME)
        names, r = self.visible_names()
        self.assertEqual(names, ["Near Shop", "Mid Shop"])                        # 12 km, 270 km and unmapped are hidden
        self.assertEqual([c["seller"] for c in r.context["nearby_deals"]], ["Near Shop", "Mid Shop"])
        d = [c["distance"] for c in r.context["results"]]
        self.assertRegex(d[0], r"^\d+ m away$")
        self.assertRegex(d[1], r"^\d\.\d km away$")

    def test_wider_radius_shows_more_but_never_the_impossible(self):
        self.member_at(HOME)
        self.member.search_radius_km = 25
        self.member.save()
        names, _ = self.visible_names()
        self.assertEqual(names, ["Near Shop", "Mid Shop", "Far Shop"])            # Mbarara (270 km) never appears

    def test_an_offers_own_reach_can_shrink_visibility(self):
        self.member_at(HOME)
        Offer.objects.filter(pk=self.offers["Mid Shop"].pk).update(offer_radius_km=Decimal("1.0"))
        names, _ = self.visible_names()
        self.assertEqual(names, ["Near Shop"])

    def test_side_panels_basket_and_compare_are_geo_locked_too(self):
        self.member_at(HOME)
        c = Client(); c.force_login(self.member_user)
        ctx = c.get(reverse("member")).context
        sellers = {b["seller"] for b in ctx["basket_items"]}
        self.assertEqual(sellers, {"Near Shop", "Mid Shop"})
        self.assertTrue(all("Mbarara" not in o["item_name"] and "Far" not in o["item_name"] for o in ctx["compare_options"]))

    def test_switching_enforcement_off_restores_the_old_behaviour(self):
        SystemSetting.objects.create(key="geo.enforce", value="false")
        names, r = self.visible_names()
        self.assertGreaterEqual(len(names), 4)                                    # everything, with no location at all
        self.assertFalse(r.context["geo"]["locked"])


class ClaimEnforcementTests(GeoBase):
    def test_cannot_claim_what_you_cannot_see(self):
        self.member_at(HOME)
        with self.assertRaisesMessage(ClaimError, "away"):
            claim_offer(self.member, self.offers["Far Shop"].pk)
        with self.assertRaises(ClaimError):
            claim_offer(self.member, self.offers["Mbarara Shop"].pk)
        with self.assertRaisesMessage(ClaimError, "isn't set"):
            claim_offer(self.member, self.offers["Unmapped Shop"].pk)
        self.assertEqual(OfferClaim.objects.count(), 0)
        self.offers["Far Shop"].refresh_from_db()
        self.assertEqual(self.offers["Far Shop"].quantity, 5)                      # stock untouched

    def test_can_claim_nearby(self):
        self.member_at(HOME)
        claim = claim_offer(self.member, self.offers["Near Shop"].pk)
        self.assertEqual(claim.offer, self.offers["Near Shop"])

    def test_no_location_and_stale_location_are_refused_with_clear_messages(self):
        with self.assertRaisesMessage(ClaimError, "Share your location"):
            claim_offer(self.member, self.offers["Near Shop"].pk)
        self.member_at(HOME, age_min=240)
        with self.assertRaisesMessage(ClaimError, "out of date"):
            claim_offer(self.member, self.offers["Near Shop"].pk)
        self.member_at(HOME, source="area", age_min=240)                          # a chosen area never goes stale
        self.assertTrue(claim_offer(self.member, self.offers["Near Shop"].pk))

    def test_claim_api_returns_the_reason(self):
        self.member_at(HOME)
        c = Client(); c.force_login(self.member_user)
        r = post(c, reverse("claims:claim_offer", args=[self.offers["Far Shop"].pk]))
        self.assertEqual(r.status_code, 400)
        self.assertIn("km", json.dumps(r.json()))


class LocationApiTests(GeoBase):
    def setUp(self):
        super().setUp()
        self.c = Client()
        self.c.force_login(self.member_user)

    def loc(self, **body):
        return post(self.c, reverse("hub_api:geo_location"), {"role": "member", **body})

    def test_sharing_stores_a_rounded_point_and_unlocks_the_page(self):
        r = self.loc(lat=0.32904321, lng=32.64897654, accuracy=25)
        self.assertEqual(r.status_code, 200, r.content)
        self.member.refresh_from_db()
        self.assertEqual((self.member.latitude, self.member.longitude), (Decimal("0.329000"), Decimal("32.649000")))   # ~110 m
        self.assertEqual(self.member.location_source, "gps")
        self.assertFalse(self.c.get(reverse("member")).context["geo"]["locked"])

    def test_bad_input_is_rejected(self):
        for body in ({"lat": "abc", "lng": 1}, {"lat": 0, "lng": 0}, {"lat": 95, "lng": 10}, {"lat": 1, "lng": 190},
                     {"lat": "nan", "lng": 5}, {"lat": None, "lng": None}, {}):
            self.assertEqual(self.loc(**body).status_code, 400, body)
        self.member.refresh_from_db()
        self.assertIsNone(self.member.latitude)

    def test_inaccurate_readings_are_refused(self):
        r = self.loc(lat=0.329, lng=32.649, accuracy=20000)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["error"]["code"], "LOW_ACCURACY")

    def test_must_be_signed_in_and_have_the_role_and_csrf(self):
        anon = Client()
        self.assertIn(post(anon, reverse("hub_api:geo_location"), {"lat": 1, "lng": 1}).status_code, (401, 403))
        self.assertEqual(self.loc(role="rider", lat=0.3, lng=32.6).status_code, 403)       # member isn't a rider
        self.assertEqual(self.loc(role="hacker", lat=0.3, lng=32.6).status_code, 400)
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.member_user)
        self.assertEqual(post(strict, reverse("hub_api:geo_location"), {"lat": 0.3, "lng": 32.6}).status_code, 403)

    def test_pick_an_area_instead_of_gps(self):
        r = post(self.c, reverse("hub_api:geo_area"), {"area_id": self.home_area.pk})
        self.assertEqual(r.status_code, 200)
        self.member.refresh_from_db()
        self.assertEqual(self.member.location_source, "area")
        ctx = self.c.get(reverse("member"), {"q": "Rice"}).context
        self.assertIn("(approx.)", ctx["results"][0]["distance"])
        self.assertEqual(post(self.c, reverse("hub_api:geo_area"), {"area_id": self.unmapped_area.pk}).json()["error"]["code"], "AREA_UNMAPPED")
        self.assertEqual(post(self.c, reverse("hub_api:geo_area"), {"area_id": 999999}).status_code, 400)

    def test_radius_choices_are_validated(self):
        self.assertEqual(post(self.c, reverse("hub_api:geo_radius"), {"radius_km": 10}).status_code, 200)
        self.member.refresh_from_db()
        self.assertEqual(self.member.search_radius_km, 10)
        for bad in (7, 0, -1, "x", 999):
            self.assertEqual(post(self.c, reverse("hub_api:geo_radius"), {"radius_km": bad}).status_code, 400, bad)

    def test_stop_sharing_wipes_the_stored_point(self):
        self.member_at(HOME)
        self.assertEqual(post(self.c, reverse("hub_api:geo_clear"), {"role": "member"}).status_code, 200)
        self.member.refresh_from_db()
        self.assertEqual((self.member.latitude, self.member.longitude, self.member.location_updated_at), (None, None, None))
        self.assertTrue(self.c.get(reverse("member")).context["geo"]["locked"])

    def test_a_teleporting_member_is_logged_not_blocked(self):
        self.member_at(HOME)
        self.assertEqual(self.loc(lat=-0.6072, lng=30.6545).status_code, 200)
        from core.models import RiskEvent
        self.assertTrue(RiskEvent.objects.filter(event_type="location_jump", user=self.member_user).exists())


class MerchantLocationTests(GeoBase):
    def test_a_shop_with_no_location_anywhere_cannot_post_offers(self):
        with self.assertRaisesMessage(OfferError, "shop location"):
            create_offer(self.ghost, item_name="X", category=self.cat, area=self.unmapped_area, normal_price=2000,
                         member_price=1500, quantity=2, expires_at=timezone.now() + timedelta(days=1))

    def test_an_area_centre_is_good_enough_to_start_and_marked_approximate(self):
        u = User.objects.create_user(phone="+256770188888", password="x", role=Role.MERCHANT)
        m = Merchant.objects.create(user=u, business_name="Area Only", category=self.cat, area=self.home_area, status=Merchant.Status.VERIFIED)
        self.assertEqual(geoservice.merchant_location_state(m)["state"], "approx")
        self.assertTrue(create_offer(m, item_name="Y", category=self.cat, area=self.home_area, normal_price=2000, member_price=1500,
                                     quantity=2, expires_at=timezone.now() + timedelta(days=1)))

    def test_merchant_sets_the_shop_location_from_the_device(self):
        c = Client(); c.force_login(self.ghost.user)
        r = post(c, reverse("hub_api:geo_location"), {"role": "merchant", "lat": 0.31234567, "lng": 32.61234567})
        self.assertEqual(r.status_code, 200, r.content)
        self.ghost.refresh_from_db()
        self.assertEqual((self.ghost.latitude, self.ghost.longitude, self.ghost.location_source),
                         (Decimal("0.312350"), Decimal("32.612350"), "gps"))
        self.assertTrue(AuditLog.objects.filter(action="merchant_location_set").exists())
        page = c.get(reverse("merchant"))
        self.assertContains(page, "Shop location: set")


class RiderGeoTests(GeoBase):
    def setUp(self):
        super().setUp()
        self.ru = User.objects.create_user(phone="+256770155555", password="x", role=Role.RIDER)
        self.rider = Rider.objects.create(user=self.ru, area=self.home_area, status=Rider.Status.VERIFIED)
        self.job_near = self.job(self.near)
        self.job_far = self.job(self.far)

    def job(self, merchant):
        return DeliveryJob.objects.create(pickup_merchant=merchant, dropoff_area=self.home_area, dropoff_address="Plot 1", fare=3000)

    def rider_at(self, point, age_min=0):
        self.rider.latitude, self.rider.longitude = Decimal(str(round(point[0], 4))), Decimal(str(round(point[1], 4)))
        self.rider.location_updated_at = timezone.now() - timedelta(minutes=age_min)
        self.rider.save()

    def board(self):
        c = Client(); c.force_login(self.ru)
        r = c.get(reverse("rider"))
        self.assertEqual(r.status_code, 200)
        return [j["from"] for j in r.context["jobs"]], r.context["geo"]

    def test_board_shows_only_jobs_near_the_rider(self):
        self.rider_at(at(0.5))
        jobs, g = self.board()
        self.assertEqual(jobs, ["Near Shop"])
        self.assertEqual((g["state"], g["hidden_far"]), ("live", 1))

    def test_no_live_location_means_no_open_jobs(self):
        self.assertEqual(self.board()[0], [])
        self.rider_at(at(0.5), age_min=60)
        jobs, g = self.board()
        self.assertEqual((jobs, g["state"]), ([], "stale"))

    def test_accepting_requires_being_close_and_live(self):
        with self.assertRaisesMessage(DeliveryError, "location sharing"):
            accept_job(self.rider, self.job_near.pk)
        self.rider_at(at(0.5))
        with self.assertRaisesMessage(DeliveryError, "within 5 km"):
            accept_job(self.rider, self.job_far.pk)
        self.job_far.refresh_from_db()
        self.assertIsNone(self.job_far.rider)
        self.assertEqual(accept_job(self.rider, self.job_near.pk).rider, self.rider)

    def test_rider_cannot_teleport_to_grab_a_job(self):
        self.rider_at(at(0.5))
        c = Client(); c.force_login(self.ru)
        r = post(c, reverse("hub_api:geo_location"), {"role": "rider", "lat": -0.6072, "lng": 30.6545})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["error"]["code"], "LOCATION_JUMP")

    def test_members_see_a_rider_count_but_never_rider_coordinates(self):
        self.rider_at(at(1.0))
        self.member_at(HOME)
        c = Client(); c.force_login(self.member_user)
        r = c.get(reverse("member"))
        self.assertEqual(r.context["riders_nearby"], 1)
        html = r.content.decode()
        self.assertNotIn(str(self.rider.latitude), html)
        self.assertNotIn(str(self.rider.longitude), html)

    def test_rider_count_ignores_stale_unavailable_unverified_and_far_riders(self):
        p = geoservice.Point(*HOME)
        self.rider_at(at(1.0))
        self.assertEqual(geoservice.riders_near(p, 5), 1)
        self.rider_at(at(1.0), age_min=60)
        self.assertEqual(geoservice.riders_near(p, 5), 0)                            # stale
        self.rider_at(at(1.0))
        Rider.objects.filter(pk=self.rider.pk).update(is_available=False)
        self.assertEqual(geoservice.riders_near(p, 5), 0)                            # off duty
        Rider.objects.filter(pk=self.rider.pk).update(is_available=True, status=Rider.Status.PENDING)
        self.assertEqual(geoservice.riders_near(p, 5), 0)                            # not verified
        Rider.objects.filter(pk=self.rider.pk).update(status=Rider.Status.VERIFIED)
        self.rider_at(at(20.0))
        self.assertEqual(geoservice.riders_near(p, 5), 0)                            # too far


class PrivacyAndAdminTests(GeoBase):
    def test_one_members_location_never_appears_on_another_members_page(self):
        self.member_at(HOME)
        other_u = User.objects.create_user(phone="+256770199999", password="x", role=Role.MEMBER)
        other = Member.objects.create(user=other_u, area=self.home_area, latitude=Decimal("0.111"), longitude=Decimal("32.222"),
                                      location_source="gps", location_updated_at=timezone.now())
        c = Client(); c.force_login(self.member_user)
        html = c.get(reverse("member")).content.decode()
        self.assertNotIn("0.111", html)
        self.assertNotIn("32.222", html)

    def test_security_headers_allow_geolocation_only_for_our_own_pages(self):
        r = Client().get(reverse("landing"))
        self.assertIn("geolocation=(self)", r["Permissions-Policy"])
        self.assertIn("connect-src 'self'", r["Content-Security-Policy"])

    def test_admin_can_correct_area_positions_with_audit_and_validation(self):
        admin = User.objects.create_user(phone="+256770100999", password="x", role=Role.SUPER_ADMIN, is_superuser=True)
        c = Client(); c.force_login(admin)
        url = reverse("hub_api:admin_area_coordinates", args=[self.unmapped_area.pk])
        r = c.patch(url, json.dumps({"latitude": 0.4, "longitude": 32.5}), content_type="application/json")
        self.assertEqual(r.status_code, 200, r.content)
        self.unmapped_area.refresh_from_db()
        self.assertEqual(self.unmapped_area.latitude, Decimal("0.400000"))
        self.assertTrue(AuditLog.objects.filter(action="area_coordinates_changed").exists())
        self.assertEqual(c.patch(url, json.dumps({"latitude": 99, "longitude": 1}), content_type="application/json").status_code, 400)
        self.assertContains(c.get(reverse("admin_settings")), "Area map positions")
        c.force_login(self.member_user)
        self.assertEqual(c.patch(url, json.dumps({"latitude": 0.4, "longitude": 32.5}), content_type="application/json").status_code, 403)

    def test_the_settings_are_read_and_bad_values_fall_back_to_safe_defaults(self):
        SystemSetting.objects.create(key="geo.default_radius_km", value="2")
        SystemSetting.objects.create(key="geo.max_radius_km", value="banana")
        SystemSetting.objects.create(key="geo.rider_job_radius_km", value="-4")
        gs = geoservice.geo_settings()
        self.assertEqual((gs.default_radius_km, gs.max_radius_km, gs.rider_job_radius_km), (2.0, 25.0, 5.0))
        self.member_at(HOME)
        self.assertEqual(geoservice.member_radius_km(self.member, gs), 2.0)
