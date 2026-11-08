import json
from datetime import datetime, timedelta
from decimal import Decimal
from unittest import mock

from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import Role, User
from claims.services import claim_offer
from core.models import Area, AuditLog
from deliveries.models import DeliveryJob
from deliveries.services import (
    accept_job, mark_arrived, mark_on_route, mark_picked_up, request_delivery,
)
from geo.models import LocationHistory, UserLocation
from geo.services import alerts, geocoding, history, nearby, routing
from geo.utils import distance_label, haversine_km, in_uganda, valid_coords
from members.models import Member
from merchants.models import Merchant
from notifications.models import Notification, NotificationCategory, NotificationPreference, PushSubscription
from offers.models import Offer, OfferCategory
from riders.models import Rider

KIREKA = (0.3464, 32.6475)
ENTEBBE = (0.0512, 32.4637)


class GeoWorld(TestCase):
    """Two areas ~40 km apart, a member in Kireka, a rider, and one offer in each area."""

    def setUp(self):
        from django.core.cache import cache
        cache.clear()                      # routes / geocodes / throttles are cached: keep tests independent
        self.kireka = Area.objects.create(name="Kireka", latitude=KIREKA[0], longitude=KIREKA[1])
        self.entebbe = Area.objects.create(name="Entebbe", latitude=ENTEBBE[0], longitude=ENTEBBE[1])
        self.cat = OfferCategory.objects.create(key="soap", label="Soap")

        self.m_user_a = User.objects.create_user(phone="+256700110001", password="pass12345", role=Role.MERCHANT)
        self.shop_a = Merchant.objects.create(
            user=self.m_user_a, business_name="Kireka Mart", category=self.cat, area=self.kireka,
            status=Merchant.Status.VERIFIED, latitude=Decimal("0.347000"), longitude=Decimal("32.648000"))
        self.m_user_b = User.objects.create_user(phone="+256700110002", password="pass12345", role=Role.MERCHANT)
        self.shop_b = Merchant.objects.create(
            user=self.m_user_b, business_name="Entebbe Mart", category=self.cat, area=self.entebbe,
            status=Merchant.Status.VERIFIED)           # no pin: falls back to the area centre

        self.user = User.objects.create_user(phone="+256700110003", password="pass12345", role=Role.MEMBER)
        self.member = Member.objects.create(user=self.user, area=self.kireka)
        self.rider_user = User.objects.create_user(phone="+256700110004", password="pass12345", role=Role.RIDER)
        self.rider = Rider.objects.create(user=self.rider_user, area=self.kireka, status=Rider.Status.VERIFIED)

        self.near = self._offer(self.shop_a, self.kireka, "Near soap")
        self.far = self._offer(self.shop_b, self.entebbe, "Far soap")

    def _offer(self, shop, area, name, **kw):
        defaults = dict(merchant=shop, category=self.cat, area=area, item_name=name, normal_price=3000,
                        member_price=2500, quantity=5, expires_at=timezone.now() + timedelta(days=1),
                        status=Offer.Status.ACTIVE, delivery_available=True)
        defaults.update(kw)
        return Offer.objects.create(**defaults)


class UtilsTests(TestCase):
    def test_haversine_kampala_to_entebbe(self):
        km = haversine_km(0.3476, 32.5825, *ENTEBBE)
        self.assertTrue(33 < km < 40, km)

    def test_valid_coords_rejects_garbage(self):
        for bad in [(None, None), ("a", "b"), (float("nan"), 1), (95, 10), (10, 200), ("", "")]:
            self.assertIsNone(valid_coords(*bad), bad)
        self.assertEqual(valid_coords("0.35", "32.6"), (0.35, 32.6))

    def test_uganda_box(self):
        self.assertTrue(in_uganda(*KIREKA))
        self.assertFalse(in_uganda(0.0, 0.0))        # the classic "null island" default
        self.assertFalse(in_uganda(51.5, -0.12))

    def test_distance_label(self):
        self.assertEqual(distance_label(0.3), "300 m away")
        self.assertEqual(distance_label(2.44), "2.4 km away")
        self.assertEqual(distance_label(None), "")


class OriginAndRankingTests(GeoWorld):
    def test_member_area_is_the_default_origin(self):
        o = nearby.resolve_origin(self.user)
        self.assertEqual((o.source, o.area.name), ("member_area", "Kireka"))
        self.assertEqual(o.label, "Kireka")

    def test_anonymous_without_coordinates_has_no_origin(self):
        self.assertIsNone(nearby.resolve_origin(None))

    def test_gps_origin_beats_everything_and_snaps_to_nearest_area(self):
        o = nearby.resolve_origin(self.user, ENTEBBE[0], ENTEBBE[1])
        self.assertEqual((o.source, o.area.name, o.label), ("gps", "Entebbe", "Near Entebbe"))

    def test_gps_outside_uganda_is_ignored(self):
        o = nearby.resolve_origin(self.user, 51.5, -0.12)
        self.assertEqual(o.source, "member_area")

    def test_manual_area_override(self):
        history.update_settings(self.user, area_override=self.entebbe)
        o = nearby.resolve_origin(self.user)
        self.assertEqual((o.source, o.area.name), ("manual_area", "Entebbe"))

    def test_saved_fix_used_only_when_shared_and_fresh(self):
        history.update_settings(self.user, share_location=True)
        history.record_fix(self.user, *ENTEBBE)
        self.assertEqual(nearby.resolve_origin(self.user).source, "saved")
        UserLocation.objects.filter(user=self.user).update(located_at=timezone.now() - timedelta(hours=5))
        self.assertEqual(nearby.resolve_origin(self.user).source, "member_area")   # stale: ignored

    def test_nearest_ranks_first_and_far_is_not_within(self):
        origin = nearby.resolve_origin(self.user)
        ranked = nearby.rank_offers([self.far, self.near], origin, limit=5)
        self.assertEqual([r.offer.item_name for r in ranked], ["Near soap", "Far soap"])
        self.assertTrue(ranked[0].within)
        self.assertFalse(ranked[1].within)
        self.assertLess(ranked[0].km, 1.0)
        self.assertGreater(ranked[1].km, 30)

    def test_include_further_false_returns_only_nearby(self):
        origin = nearby.resolve_origin(self.user)
        ranked = nearby.rank_offers([self.far, self.near], origin, include_further=False)
        self.assertEqual([r.offer.item_name for r in ranked], ["Near soap"])

    def test_merchant_radius_geo_lock(self):
        locked = self._offer(self.shop_b, self.entebbe, "Entebbe only", offer_radius_km=Decimal("2.0"))
        origin = nearby.resolve_origin(self.user)                       # standing in Kireka, ~40 km away
        names = [r.offer.item_name for r in nearby.rank_offers([locked, self.near], origin, limit=5)]
        self.assertEqual(names, ["Near soap"])                          # hidden on discovery surfaces
        kept = nearby.rank_offers([locked], origin, apply_lock=False)   # member search keeps it, flagged
        self.assertTrue(kept[0].locked)
        # standing in Entebbe the same offer is visible
        here = nearby.resolve_origin(self.user, *ENTEBBE)
        self.assertEqual([r.offer.item_name for r in nearby.rank_offers([locked], here)], ["Entebbe only"])

    def test_hot_score_prefers_bigger_discount_at_same_distance(self):
        deep = self._offer(self.shop_a, self.kireka, "Deep discount", member_price=1000)
        origin = nearby.resolve_origin(self.user)
        ranked = nearby.rank_offers([self.near, deep], origin, limit=5)
        self.assertEqual(ranked[0].offer.item_name, "Deep discount")

    def test_pinned_vs_area_centre_precision_flags(self):
        origin = nearby.resolve_origin(self.user, *KIREKA)
        by_name = {r.offer.item_name: r for r in nearby.rank_offers([self.near, self.far], origin, limit=5)}
        self.assertTrue(by_name["Near soap"].precise)           # GPS + pinned shop
        self.assertFalse(by_name["Far soap"].precise)           # shop never pinned: area centre
        self.assertTrue(by_name["Far soap"].distance_text.startswith("≈"))


class LandingPageTests(GeoWorld):
    def test_signed_in_member_gets_their_area_first(self):
        self.client.force_login(self.user)
        html = self.client.get(reverse("landing")).content.decode()
        self.assertIn("Hot deals · Kireka", html)
        self.assertLess(html.index("Near soap"), html.index("Far soap"))

    def test_member_in_another_area_sees_that_area_first(self):
        history.update_settings(self.user, area_override=self.entebbe)
        self.client.force_login(self.user)
        html = self.client.get(reverse("landing")).content.decode()
        self.assertIn("Hot deals · Entebbe", html)
        self.assertLess(html.index("Far soap"), html.index("Near soap"))

    def test_anonymous_gets_generic_heading_and_the_locate_button(self):
        html = self.client.get(reverse("landing")).content.decode()
        self.assertIn("Today&#x27;s hot deals", html.replace("'", "&#x27;"))
        self.assertIn("data-geo-locate", html)
        self.assertIn('data-authenticated="0"', html)

    def test_leaflet_and_geo_scripts_are_self_hosted(self):
        html = self.client.get(reverse("landing")).content.decode()
        self.assertIn("hub/vendor/leaflet/leaflet.js", html)
        self.assertIn("hub/js/geo.js", html)
        self.assertNotIn("unpkg.com", html)

    def test_tiles_are_told_to_send_the_origin_as_referrer(self):
        """OSM answers "403 Access blocked" to tile requests without a Referer, and our global policy sends none."""
        html = self.client.get(reverse("landing")).content.decode()
        self.assertIn('data-tile-referrer="origin"', html)
        r = self.client.get(reverse("landing"))
        self.assertEqual(r["Referrer-Policy"], "same-origin")      # the site-wide privacy policy is unchanged

    def test_map_data_is_embedded_for_the_map_view(self):
        self.client.force_login(self.user)
        html = self.client.get(reverse("landing")).content.decode()
        self.assertIn('id="landing-map-data"', html)


class NearbyDealsApiTests(GeoWorld):
    url = "/api/v1/geo/nearby-deals/"

    def test_public_with_gps_ranks_by_distance(self):
        data = self.client.get(self.url, {"lat": ENTEBBE[0], "lng": ENTEBBE[1]}).json()["data"]
        self.assertEqual(data["origin"]["source"], "gps")
        self.assertEqual(data["deals"][0]["item"], "Far soap")          # the Entebbe deal is nearest to Entebbe
        self.assertNotIn("phone", json.dumps(data))

    def test_without_origin_still_returns_deals(self):
        data = self.client.get(self.url).json()["data"]
        self.assertIsNone(data["origin"])
        self.assertEqual(len(data["deals"]), 2)

    def test_bad_params_do_not_crash(self):
        for qs in ({"lat": "abc", "lng": "x"}, {"limit": "zzz"}, {"radius": "huge"}, {"lat": 95, "lng": 500}):
            self.assertEqual(self.client.get(self.url, qs).status_code, 200, qs)

    def test_gps_query_is_not_stored(self):
        self.client.force_login(self.user)
        self.client.get(self.url, {"lat": ENTEBBE[0], "lng": ENTEBBE[1]})
        self.assertFalse(UserLocation.objects.filter(user=self.user, latitude__isnull=False).exists())
        self.assertFalse(LocationHistory.objects.exists())


class ConsentAndHistoryTests(GeoWorld):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)

    def ping(self, lat, lng, **extra):
        return self.client.post("/api/v1/geo/me/ping/", {"lat": lat, "lng": lng, **extra}, content_type="application/json")

    def test_defaults_are_private(self):
        data = self.client.get("/api/v1/geo/me/").json()["data"]
        self.assertFalse(data["share_location"])
        self.assertFalse(data["save_history"])

    def test_ping_without_consent_stores_nothing_but_names_the_area(self):
        r = self.ping(*KIREKA).json()["data"]
        self.assertEqual((r["area"], r["stored"], r["history"]), ("Kireka", False, False))
        self.assertFalse(LocationHistory.objects.exists())
        self.assertIsNone(UserLocation.objects.get(user=self.user).latitude)

    def test_sharing_stores_last_fix_but_not_history(self):
        self.client.patch("/api/v1/geo/me/", {"share_location": True}, content_type="application/json")
        r = self.ping(*KIREKA).json()["data"]
        self.assertTrue(r["stored"])
        self.assertFalse(r["history"])
        self.assertFalse(LocationHistory.objects.exists())

    def test_history_is_a_second_opt_in_and_deduplicated(self):
        self.client.patch("/api/v1/geo/me/", {"share_location": True, "save_history": True}, content_type="application/json")
        self.ping(*KIREKA)
        self.ping(KIREKA[0] + 0.00001, KIREKA[1])         # ~1 m away, seconds later: no new row
        self.assertEqual(LocationHistory.objects.filter(user=self.user).count(), 1)
        self.ping(*ENTEBBE)                                # moved 40 km: new row
        self.assertEqual(LocationHistory.objects.filter(user=self.user).count(), 2)

    def test_history_precision_is_rounded(self):
        self.client.patch("/api/v1/geo/me/", {"share_location": True, "save_history": True}, content_type="application/json")
        self.ping(0.346412345, 32.647598765)
        row = LocationHistory.objects.get()
        self.assertEqual((row.latitude, row.longitude), (Decimal("0.346400"), Decimal("32.647600")))

    def test_turning_sharing_off_forgets_the_fix_and_the_trail_switch(self):
        self.client.patch("/api/v1/geo/me/", {"share_location": True, "save_history": True}, content_type="application/json")
        self.ping(*KIREKA)
        data = self.client.patch("/api/v1/geo/me/", {"share_location": False}, content_type="application/json").json()["data"]
        self.assertFalse(data["save_history"])
        self.assertIsNone(data["last_fix"])

    def test_cannot_enable_history_without_sharing(self):
        data = self.client.patch("/api/v1/geo/me/", {"save_history": True}, content_type="application/json").json()["data"]
        self.assertFalse(data["save_history"])

    def test_outside_uganda_and_garbage_rejected(self):
        self.assertEqual(self.ping(51.5, -0.12).status_code, 400)
        self.assertEqual(self.ping("x", "y").status_code, 400)
        self.assertEqual(self.ping(0, 0).status_code, 400)

    def test_user_can_list_delete_one_clear_all_and_export(self):
        self.client.patch("/api/v1/geo/me/", {"share_location": True, "save_history": True}, content_type="application/json")
        self.ping(*KIREKA); self.ping(*ENTEBBE)
        rows = self.client.get("/api/v1/geo/me/history/").json()["data"]["history"]
        self.assertEqual(len(rows), 2)
        self.assertEqual(self.client.delete(f"/api/v1/geo/me/history/{rows[0]['id']}/").status_code, 200)
        export = self.client.get("/api/v1/geo/me/history/export/").json()["data"]
        self.assertEqual(len(export["history"]), 1)
        self.assertEqual(self.client.delete("/api/v1/geo/me/history/").json()["data"]["deleted"], 1)
        self.assertFalse(LocationHistory.objects.filter(user=self.user).exists())

    def test_cannot_touch_someone_elses_history(self):
        other = User.objects.create_user(phone="+256700110099", password="x", role=Role.MEMBER)
        row = LocationHistory.objects.create(user=other, latitude=Decimal("0.3"), longitude=Decimal("32.6"))
        self.assertEqual(self.client.delete(f"/api/v1/geo/me/history/{row.pk}/").status_code, 404)
        self.assertTrue(LocationHistory.objects.filter(pk=row.pk).exists())
        self.assertEqual(self.client.get("/api/v1/geo/me/history/").json()["data"]["history"], [])

    def test_endpoints_require_login(self):
        self.client.logout()
        for url in ("/api/v1/geo/me/", "/api/v1/geo/me/history/", "/api/v1/geo/geocode/?q=abc", "/api/v1/geo/route/"):
            self.assertIn(self.client.get(url).status_code, (401, 403), url)

    def test_area_override_validates_the_area(self):
        self.assertEqual(self.client.patch("/api/v1/geo/me/", {"area_override": 99999}, content_type="application/json").status_code, 400)
        ok = self.client.patch("/api/v1/geo/me/", {"area_override": self.entebbe.pk}, content_type="application/json").json()["data"]
        self.assertEqual(ok["area_override"]["name"], "Entebbe")

    def test_purge_respects_retention_and_rider_rows_are_shorter(self):
        old = timezone.now() - timedelta(days=40)
        a = LocationHistory.objects.create(user=self.user, latitude=Decimal("0.3"), longitude=Decimal("32.6"))
        b = LocationHistory.objects.create(user=self.user, latitude=Decimal("0.3"), longitude=Decimal("32.6"))
        r = LocationHistory.objects.create(user=self.rider_user, latitude=Decimal("0.3"), longitude=Decimal("32.6"),
                                           source=LocationHistory.Source.RIDER_LIVE)
        LocationHistory.objects.filter(pk=a.pk).update(created_at=old)
        LocationHistory.objects.filter(pk=r.pk).update(created_at=timezone.now() - timedelta(days=8))
        res = history.purge_expired()
        self.assertEqual((res["history"], res["rider_live"]), (1, 1))
        self.assertEqual(list(LocationHistory.objects.values_list("pk", flat=True)), [b.pk])

    def test_member_page_shows_location_card(self):
        html = self.client.get(reverse("member")).content.decode()
        self.assertIn('id="location"', html)
        self.assertIn("data-geo-setting=\"share_location\"", html)
        self.assertIn("data-geo-area", html)


class GeocodingAndRoutingTests(GeoWorld):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)

    def test_search_finds_areas_and_pinned_shops_without_any_network(self):
        res = self.client.get("/api/v1/geo/geocode/", {"q": "kire"}).json()["data"]
        labels = [r["label"] for r in res["results"]]
        self.assertIn("Kireka (area centre)", labels)
        self.assertIn("Kireka Mart", labels)
        self.assertTrue(res["available"])           # geocoder switched off by config != outage

    def test_short_queries_return_nothing(self):
        self.assertEqual(self.client.get("/api/v1/geo/geocode/", {"q": "ki"}).json()["data"]["results"], [])

    @override_settings(GEOCODER_BASE_URL="https://geo.example.test")
    def test_remote_results_are_filtered_cached_and_tagged_with_area(self):
        payload = [{"display_name": "Kireka Market, Kireka, Wakiso, Uganda", "lat": "0.3470", "lon": "32.6480"},
                   {"display_name": "Somewhere in London", "lat": "51.5", "lon": "-0.12"}]
        resp = mock.Mock(); resp.raise_for_status = lambda: None; resp.json = lambda: payload
        with mock.patch("geo.services.geocoding.requests.get", return_value=resp) as get:
            r1 = geocoding.search("kireka market")
            from django.core.cache import cache
            cache.delete("geo:geocoder-slot")
            r2 = geocoding.search("kireka market")
        self.assertEqual(get.call_count, 1)                          # second call served from cache
        remote = [x for x in r1["results"] if x["kind"] == "address"]
        self.assertEqual(len(remote), 1)                             # London dropped
        self.assertEqual(remote[0]["area"], "Kireka")
        self.assertEqual(r1["results"], r2["results"])

    @override_settings(GEOCODER_BASE_URL="https://geo.example.test")
    def test_geocoder_outage_falls_back_to_local_data_and_says_so(self):
        import requests as rq
        from django.core.cache import cache
        cache.delete("geo:geocoder-slot")
        with mock.patch("geo.services.geocoding.requests.get", side_effect=rq.ConnectionError("down")):
            r = geocoding.search("kireka")
        self.assertFalse(r["available"])
        self.assertTrue(r["results"])                                # still the local matches

    def test_reverse_falls_back_to_nearest_area_label(self):
        r = self.client.get("/api/v1/geo/reverse/", {"lat": 0.3470, "lng": 32.6480}).json()["data"]
        self.assertEqual((r["label"], r["area"], r["approximate"]), ("Near Kireka", "Kireka", True))

    def test_reverse_rejects_places_outside_uganda(self):
        self.assertEqual(self.client.get("/api/v1/geo/reverse/", {"lat": 51.5, "lng": -0.1}).status_code, 400)

    def test_route_estimate_when_no_router_is_configured(self):
        r = self.client.get("/api/v1/geo/route/", {"from_lat": KIREKA[0], "from_lng": KIREKA[1],
                                                   "to_lat": 0.3600, "to_lng": 32.6600}).json()["data"]
        self.assertEqual(r["source"], "estimate")
        self.assertGreater(r["distance_km"], 1)
        self.assertGreaterEqual(r["duration_min"], 1)
        self.assertEqual(len(r["geometry"]), 2)
        self.assertIn("eta_at", r)

    def test_route_validates_inputs(self):
        self.assertEqual(self.client.get("/api/v1/geo/route/", {"from_lat": 1}).status_code, 400)
        self.assertEqual(self.client.get("/api/v1/geo/route/", {"from_lat": 51, "from_lng": 0, "to_lat": 0.3, "to_lng": 32.6}).status_code, 400)

    @override_settings(OSRM_BASE_URL="https://router.example.test")
    def test_osrm_geometry_is_converted_from_lnglat_to_latlng(self):
        body = {"routes": [{"distance": 2500, "duration": 330,
                            "geometry": {"coordinates": [[32.6475, 0.3464], [32.6500, 0.3480], [32.6600, 0.3600]]}}]}
        resp = mock.Mock(); resp.raise_for_status = lambda: None; resp.json = lambda: body
        from django.core.cache import cache
        cache.clear()
        with mock.patch("geo.services.routing.requests.get", return_value=resp) as get:
            r = routing.route(KIREKA, (0.3600, 32.6600))
        self.assertIn("32.6475,0.3464;32.66,0.36", get.call_args[0][0])      # OSRM wants lng,lat
        self.assertEqual((r["source"], r["distance_km"], r["duration_min"]), ("osrm", 2.5, 6))
        self.assertEqual(r["geometry"][0], [0.3464, 32.6475])               # we return lat,lng

    @override_settings(OSRM_BASE_URL="https://router.example.test")
    def test_osrm_failure_degrades_to_estimate(self):
        import requests as rq
        from django.core.cache import cache
        cache.clear()
        with mock.patch("geo.services.routing.requests.get", side_effect=rq.Timeout()):
            r = routing.route(KIREKA, (0.36, 32.66))
        self.assertEqual(r["source"], "estimate")


class DropoffTests(GeoWorld):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)
        self.claim = claim_offer(self.member, self.near.id)

    def post(self, **extra):
        body = {"claim_code": self.claim.code, "dropoff_area": "Kireka", "dropoff_address": "Near the market",
                "delivery_type": "normal", "payment_method": "cash", **extra}
        return self.client.post(reverse("deliveries:request_delivery"), body, content_type="application/json")

    def test_member_page_offers_address_search_and_pin_when_a_claim_is_deliverable(self):
        html = self.client.get(reverse("member")).content.decode()
        self.assertIn("data-geocode-input", html)
        self.assertIn('name="dropoff_lat"', html)
        self.assertIn('data-lat="0.346400"', html)             # area centres for the map to start from

    def test_without_coordinates_works_exactly_as_before(self):
        r = self.post()
        self.assertEqual(r.status_code, 201, r.content)
        job = DeliveryJob.objects.get()
        self.assertIsNone(job.dropoff_latitude)

    def test_valid_pin_is_stored_and_flagged(self):
        r = self.post(dropoff_lat=0.3480, dropoff_lng=32.6490, dropoff_geocoded="true")
        self.assertEqual(r.status_code, 201, r.content)
        job = DeliveryJob.objects.get()
        self.assertEqual((job.dropoff_latitude, job.dropoff_longitude), (Decimal("0.348000"), Decimal("32.649000")))
        self.assertTrue(job.dropoff_geocoded)

    def test_pin_far_from_the_chosen_area_is_refused(self):
        r = self.post(dropoff_lat=ENTEBBE[0], dropoff_lng=ENTEBBE[1])
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["error"]["code"], "DROPOFF_TOO_FAR")
        self.assertFalse(DeliveryJob.objects.exists())

    def test_pin_outside_uganda_or_garbage_is_refused(self):
        for lat, lng in [(0, 0), (51.5, -0.1), ("abc", "def"), (0.3, "")]:
            r = self.post(dropoff_lat=lat, dropoff_lng=lng)
            self.assertEqual(r.status_code, 400, (lat, lng))
            self.assertEqual(r.json()["error"]["code"], "INVALID_LOCATION")

    def test_dropoff_enters_history_only_with_consent(self):
        self.post(dropoff_lat=0.3480, dropoff_lng=32.6490)
        self.assertFalse(LocationHistory.objects.exists())
        other_offer = self._offer(self.shop_a, self.kireka, "Another soap")
        self.claim2 = claim_offer(self.member, other_offer.id)
        history.update_settings(self.user, share_location=True, save_history=True)
        self.client.post(reverse("deliveries:request_delivery"),
                         {"claim_code": self.claim2.code, "dropoff_area": "Kireka", "dropoff_address": "Home",
                          "delivery_type": "normal", "payment_method": "cash",
                          "dropoff_lat": 0.3480, "dropoff_lng": 32.6490}, content_type="application/json")
        self.assertEqual(LocationHistory.objects.filter(source="dropoff").count(), 1)


class TrackingTests(GeoWorld):
    def setUp(self):
        super().setUp()
        self.claim = claim_offer(self.member, self.near.id)
        self.job = request_delivery(
            claim=self.claim, merchant=self.shop_a, dropoff_area=self.kireka, dropoff_address="Gate 4",
            delivery_type="normal", fare=Decimal("1500"),
            dropoff_latitude=Decimal("0.352000"), dropoff_longitude=Decimal("32.652000"), dropoff_geocoded=True)
        self.track = f"/api/v1/member/delivery/{self.job.pk}/track/"

    def _advance(self, upto):
        accept_job(self.rider, self.job.id)
        if upto == "accepted":
            return
        mark_arrived(self.rider, self.job.id)
        mark_picked_up(self.rider, self.job.id)
        if upto == "picked":
            return
        mark_on_route(self.rider, self.job.id)

    def test_member_page_renders_with_a_delivery_and_offers_tracking(self):
        """Regression: /member/ used to crash (NameError: reverse) for any member who had a delivery request."""
        self.client.force_login(self.user)
        r = self.client.get(reverse("member"))
        self.assertEqual(r.status_code, 200)
        html = r.content.decode()
        self.assertIn(f'data-track-url="/api/v1/member/delivery/{self.job.pk}/track/"', html)
        self.assertIn("data-trip-map", html)

    def test_member_sees_pickup_dropoff_and_trip_estimate_before_a_rider_is_assigned(self):
        self.client.force_login(self.user)
        d = self.client.get(self.track).json()["data"]
        self.assertEqual(d["pickup"]["label"], "Kireka Mart")
        self.assertTrue(d["pickup"]["precise"])
        self.assertEqual(d["dropoff"]["lat"], 0.352)
        self.assertEqual(d["leg"], "trip")
        self.assertIsNone(d["rider"])
        self.assertIsNone(d["eta_minutes"])

    def test_other_members_cannot_track_it(self):
        stranger = User.objects.create_user(phone="+256700110050", password="x", role=Role.MEMBER)
        Member.objects.create(user=stranger, area=self.kireka)
        self.client.force_login(stranger)
        self.assertEqual(self.client.get(self.track).status_code, 404)

    def test_riders_cannot_use_the_customer_tracking_endpoint(self):
        self.client.force_login(self.rider_user)
        self.assertEqual(self.client.get(self.track).status_code, 403)

    def test_rider_position_gives_eta_to_pickup_then_to_dropoff(self):
        self._advance("accepted")
        self.client.force_login(self.rider_user)
        r = self.client.post("/api/v1/rider/location/", {"lat": 0.3600, "lng": 32.6600}, content_type="application/json")
        self.assertTrue(r.json()["data"]["tracking"])
        self.client.force_login(self.user)
        d = self.client.get(self.track).json()["data"]
        self.assertEqual(d["leg"], "to_pickup")
        self.assertEqual(d["rider"]["lat"], 0.36)
        self.assertGreaterEqual(d["eta_minutes"], 6)                 # to shop + handover buffer + shop->drop-off

        self._advance_rest()
        d = self.client.get(self.track).json()["data"]
        self.assertEqual(d["leg"], "to_dropoff")

    def _advance_rest(self):
        mark_arrived(self.rider, self.job.id)
        mark_picked_up(self.rider, self.job.id)
        mark_on_route(self.rider, self.job.id)

    def test_rider_pings_are_ignored_without_an_active_job(self):
        self.client.force_login(self.rider_user)
        r = self.client.post("/api/v1/rider/location/", {"lat": 0.36, "lng": 32.66}, content_type="application/json")
        self.assertFalse(r.json()["data"]["tracking"])
        self.assertFalse(LocationHistory.objects.exists())

    def test_rider_ping_validates_coordinates(self):
        self._advance("accepted")
        self.client.force_login(self.rider_user)
        for lat, lng in [(0, 0), ("x", 1), (51, 0)]:
            r = self.client.post("/api/v1/rider/location/", {"lat": lat, "lng": lng}, content_type="application/json")
            self.assertEqual(r.status_code, 400, (lat, lng))

    def test_customer_is_told_once_when_the_rider_is_nearby(self):
        self._advance("on_route")
        self.client.force_login(self.rider_user)
        for _ in range(3):
            self.client.post("/api/v1/rider/location/", {"lat": 0.3515, "lng": 32.6515}, content_type="application/json")
        self.assertEqual(Notification.objects.filter(user=self.user, title="Your rider is nearby").count(), 1)

    def test_rider_far_away_does_not_trigger_nearby_notice(self):
        self._advance("on_route")
        self.client.force_login(self.rider_user)
        self.client.post("/api/v1/rider/location/", {"lat": 0.3900, "lng": 32.7000}, content_type="application/json")
        self.assertFalse(Notification.objects.filter(title="Your rider is nearby").exists())

    def test_rider_position_is_hidden_after_delivery_ends(self):
        self._advance("on_route")
        self.client.force_login(self.rider_user)
        self.client.post("/api/v1/rider/location/", {"lat": 0.3515, "lng": 32.6515}, content_type="application/json")
        DeliveryJob.objects.filter(pk=self.job.pk).update(status=DeliveryJob.Status.DELIVERED)
        self.client.force_login(self.user)
        d = self.client.get(self.track).json()["data"]
        self.assertIsNone(d["rider"])
        self.assertFalse(d["live"])

    def test_rider_nav_shows_exact_dropoff_only_to_the_assigned_rider(self):
        self.client.force_login(self.rider_user)
        nav = f"/api/v1/rider/jobs/{self.job.pk}/nav/"
        open_view = self.client.get(nav, {"lat": 0.36, "lng": 32.66}).json()["data"]
        self.assertFalse(open_view["owned"])
        self.assertFalse(open_view["dropoff"]["precise"])           # area centre only, not the exact door
        accept_job(self.rider, self.job.id)
        mine = self.client.get(nav, {"lat": 0.36, "lng": 32.66}).json()["data"]
        self.assertTrue(mine["owned"])
        self.assertTrue(mine["dropoff"]["precise"])
        self.assertEqual(mine["leg"], "to_pickup")

        other_user = User.objects.create_user(phone="+256700110060", password="x", role=Role.RIDER)
        Rider.objects.create(user=other_user, area=self.kireka, status=Rider.Status.VERIFIED)
        self.client.force_login(other_user)
        self.assertEqual(self.client.get(nav).status_code, 404)     # taken: no longer open to others

    def test_rider_fix_dedupe_keeps_table_small(self):
        self._advance("accepted")
        for _ in range(5):
            history.record_rider_fix(self.rider_user, self.job, 0.36, 32.66)
        self.assertEqual(LocationHistory.objects.filter(job=self.job).count(), 1)


class MerchantPinTests(GeoWorld):
    url = "/api/v1/merchant/location/"

    def test_merchant_can_pin_the_shop_and_it_is_audited(self):
        self.client.force_login(self.m_user_b)
        r = self.client.post(self.url, {"lat": 0.0530, "lng": 32.4650, "address": "Airport Rd"}, content_type="application/json")
        self.assertEqual(r.status_code, 200, r.content)
        self.shop_b.refresh_from_db()
        self.assertEqual(self.shop_b.latitude, Decimal("0.053000"))
        self.assertEqual(self.shop_b.address, "Airport Rd")
        self.assertTrue(AuditLog.objects.filter(action="merchant_location_set", object_id=str(self.shop_b.pk)).exists())

    def test_pin_far_from_the_merchants_area_is_refused(self):
        self.client.force_login(self.m_user_b)
        r = self.client.post(self.url, {"lat": KIREKA[0], "lng": KIREKA[1]}, content_type="application/json")
        self.assertEqual((r.status_code, r.json()["error"]["code"]), (400, "OUTSIDE_AREA"))

    def test_invalid_points_refused_and_members_forbidden(self):
        self.client.force_login(self.m_user_a)
        self.assertEqual(self.client.post(self.url, {"lat": 0, "lng": 0}, content_type="application/json").status_code, 400)
        self.client.force_login(self.user)
        self.assertEqual(self.client.post(self.url, {"lat": 0.3, "lng": 32.6}, content_type="application/json").status_code, 403)

    def test_pinning_improves_distance_precision(self):
        origin = nearby.resolve_origin(self.user, 0.0515, 32.4640)
        before = nearby.rank_offers([self.far], origin)[0]
        self.assertFalse(before.precise)
        self.client.force_login(self.m_user_b)
        self.client.post(self.url, {"lat": 0.0530, "lng": 32.4650}, content_type="application/json")
        self.far.refresh_from_db()
        after = nearby.rank_offers([Offer.objects.select_related("merchant", "merchant__area", "area").get(pk=self.far.pk)], origin)[0]
        self.assertTrue(after.precise)


VAPID = dict(VAPID_PUBLIC_KEY="BPubKeyForTests", VAPID_PRIVATE_KEY="privForTests", VAPID_CONTACT="mailto:ops@example.test")
SUB = {"endpoint": "https://fcm.googleapis.com/fcm/send/abc123", "keys": {"p256dh": "p" * 20, "auth": "a" * 10}}


@override_settings(**VAPID)
class PushTests(GeoWorld):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)

    def sub(self, **override):
        return self.client.post("/api/v1/push/subscribe/", {**SUB, **override}, content_type="application/json")

    def test_subscribe_stores_the_device(self):
        self.assertEqual(self.sub().status_code, 201)
        self.assertEqual(PushSubscription.objects.filter(user=self.user).count(), 1)

    def test_same_device_is_not_duplicated_and_moves_to_the_new_user(self):
        self.sub()
        other = User.objects.create_user(phone="+256700110077", password="x", role=Role.MEMBER)
        Member.objects.create(user=other, area=self.kireka)
        self.client.force_login(other)
        self.sub()
        self.assertEqual(PushSubscription.objects.count(), 1)
        self.assertEqual(PushSubscription.objects.get().user, other)

    def test_ssrf_guard_rejects_internal_and_non_push_endpoints(self):
        for bad in ["http://fcm.googleapis.com/x", "https://169.254.169.254/latest/meta-data",
                    "https://127.0.0.1/hook", "https://evil.example.com/push", "https://fcm.googleapis.com.evil.com/x",
                    "https://user:pw@fcm.googleapis.com/x", "ftp://fcm.googleapis.com/x", "not a url", ""]:
            self.assertEqual(self.sub(endpoint=bad).status_code, 400, bad)
        self.assertFalse(PushSubscription.objects.exists())

    def test_every_real_push_service_is_allowed(self):
        for ok in ["https://fcm.googleapis.com/fcm/send/1", "https://updates.push.services.mozilla.com/wpush/v2/1",
                   "https://web.push.apple.com/1", "https://wns2-par02p.notify.windows.com/?token=1"]:
            self.assertEqual(self.sub(endpoint=ok).status_code, 201, ok)

    def test_incomplete_subscription_is_rejected(self):
        self.assertEqual(self.sub(keys={}).status_code, 400)
        self.assertEqual(self.sub(keys={"p256dh": "x"}).status_code, 400)

    @override_settings(VAPID_PUBLIC_KEY="", VAPID_PRIVATE_KEY="")
    def test_push_is_unavailable_until_vapid_keys_exist(self):
        self.assertEqual(self.sub().status_code, 503)
        self.assertEqual(self.client.get("/api/v1/push/").json()["data"]["configured"], False)

    def test_unsubscribe_one_or_all(self):
        self.sub(); self.sub(endpoint="https://fcm.googleapis.com/fcm/send/second")
        self.client.post("/api/v1/push/unsubscribe/", {"endpoint": SUB["endpoint"]}, content_type="application/json")
        self.assertEqual(PushSubscription.objects.count(), 1)
        self.client.post("/api/v1/push/unsubscribe/", {"all": True}, content_type="application/json")
        self.assertEqual(PushSubscription.objects.count(), 0)

    def test_unsubscribe_cannot_remove_someone_elses_device(self):
        other = User.objects.create_user(phone="+256700110078", password="x", role=Role.MEMBER)
        PushSubscription.objects.create(user=other, endpoint=SUB["endpoint"], p256dh="p", auth="a")
        self.client.post("/api/v1/push/unsubscribe/", {"endpoint": SUB["endpoint"]}, content_type="application/json")
        self.assertEqual(PushSubscription.objects.count(), 1)

    def test_send_push_delivers_and_prunes_dead_subscriptions(self):
        from notifications.services import push
        PushSubscription.objects.create(user=self.user, endpoint=SUB["endpoint"], p256dh="p", auth="a")
        PushSubscription.objects.create(user=self.user, endpoint="https://fcm.googleapis.com/fcm/send/dead", p256dh="p", auth="a")
        outcomes = {SUB["endpoint"]: "ok", "https://fcm.googleapis.com/fcm/send/dead": "gone"}
        with mock.patch.object(push, "_send", side_effect=lambda sub, payload: outcomes[sub.endpoint]) as send:
            n = push.send_push(self.user, "Hi", "Body", url="/member/")
        self.assertEqual(n, 1)
        self.assertEqual(PushSubscription.objects.count(), 1)           # the dead one (410) was removed
        self.assertIsNotNone(PushSubscription.objects.get().last_success_at)
        self.assertEqual(send.call_args_list[0][0][1]["url"], "/member/")

    def test_payload_urls_are_forced_same_site_and_truncated(self):
        from notifications.services import push
        PushSubscription.objects.create(user=self.user, endpoint=SUB["endpoint"], p256dh="p", auth="a")
        with mock.patch.object(push, "_send", return_value="ok") as send:
            push.send_push(self.user, "T" * 500, "B" * 500, url="https://evil.example.com/")
        payload = send.call_args[0][1]
        self.assertEqual(payload["url"], "/")
        self.assertLessEqual(len(payload["title"]), 80)
        self.assertLessEqual(len(payload["body"]), 180)

    def test_repeated_failures_eventually_drop_the_device(self):
        from notifications.services import push
        PushSubscription.objects.create(user=self.user, endpoint=SUB["endpoint"], p256dh="p", auth="a")
        with mock.patch.object(push, "_send", return_value="error"):
            for _ in range(push.MAX_FAILURES):
                push.send_push(self.user, "x", "y")
        self.assertFalse(PushSubscription.objects.exists())

    def test_dispatch_honours_channel_restrictions(self):
        from notifications import tasks
        n = Notification.objects.create(user=self.user, category=NotificationCategory.OFFER, title="Deal", message="m",
                                        metadata={"_channels": ["in_app", "push"]})
        with mock.patch.object(tasks.send_push_notification, "delay") as push_task, \
                mock.patch.object(tasks.send_sms_notification, "delay") as sms_task:
            tasks.dispatch_external_notification(n.id)
        push_task.assert_called_once()
        sms_task.assert_not_called()                                    # promotional alert: never SMS

    def test_normal_notifications_still_use_sms_and_push(self):
        from notifications import tasks
        n = Notification.objects.create(user=self.user, category=NotificationCategory.CLAIM, title="t", message="m")
        with mock.patch.object(tasks.send_push_notification, "delay") as push_task, \
                mock.patch.object(tasks.send_sms_notification, "delay") as sms_task:
            tasks.dispatch_external_notification(n.id)
        push_task.assert_called_once()
        sms_task.assert_called_once()

    def test_push_opt_out_is_respected(self):
        from notifications import tasks
        NotificationPreference.objects.update_or_create(user=self.user, defaults={"push_enabled": False})
        n = Notification.objects.create(user=self.user, category=NotificationCategory.CLAIM, title="t", message="m")
        with mock.patch.object(tasks.send_push_notification, "delay") as push_task:
            tasks.dispatch_external_notification(n.id)
        push_task.assert_not_called()

    def test_service_worker_is_served_from_root_with_scope_header(self):
        r = self.client.get("/sw.js")
        self.assertEqual(r.status_code, 200)
        self.assertIn("javascript", r["Content-Type"])
        self.assertEqual(r["Service-Worker-Allowed"], "/")
        self.assertIn(b"showNotification", r.content)

    def test_real_pywebpush_accepts_our_generated_keys_and_signs_the_request(self):
        """Runs the real pywebpush + py-vapid code with a command-generated key pair against a realistic browser
        subscription; only the final HTTP POST is intercepted. Catches key-format incompatibilities."""
        import base64, os
        from io import StringIO
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        from django.core.management import call_command
        from notifications.services import push

        out = StringIO(); call_command("generate_vapid_keys", stdout=out)
        keys = dict(l.split("=", 1) for l in out.getvalue().splitlines() if l.startswith("VAPID_"))
        b64 = lambda b: base64.urlsafe_b64encode(b).rstrip(b"=").decode()
        browser_key = ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
        sub = PushSubscription.objects.create(
            user=self.user, endpoint="https://fcm.googleapis.com/fcm/send/real-test",
            p256dh=b64(browser_key), auth=b64(os.urandom(16)))
        resp = mock.Mock(status_code=201, ok=True)
        with override_settings(VAPID_PUBLIC_KEY=keys["VAPID_PUBLIC_KEY"], VAPID_PRIVATE_KEY=keys["VAPID_PRIVATE_KEY"].split()[0],
                               VAPID_CONTACT="mailto:ops@example.test"), \
                mock.patch("pywebpush.requests.post", return_value=resp) as post:
            outcome = push._send(sub, {"title": "Hi", "body": "There", "url": "/member/"})
        self.assertEqual(outcome, "ok")
        url = post.call_args[0][0]
        headers = post.call_args[1]["headers"]
        self.assertEqual(url, sub.endpoint)
        self.assertTrue(headers["authorization"].startswith("vapid t="), headers)   # signed VAPID JWT
        self.assertEqual(headers["content-encoding"], "aes128gcm")                   # payload is encrypted
        self.assertIsInstance(post.call_args[1]["data"], bytes)
        self.assertNotIn(b"There", post.call_args[1]["data"])                        # not sent in clear

    def test_push_service_410_means_gone(self):
        from pywebpush import WebPushException
        from notifications.services import push
        sub = PushSubscription.objects.create(user=self.user, endpoint=SUB["endpoint"], p256dh="p", auth="a")
        exc = WebPushException("gone", response=mock.Mock(status_code=410))
        with mock.patch("pywebpush.webpush", side_effect=exc):
            self.assertEqual(push._send(sub, {"title": "x"}), "gone")
        exc500 = WebPushException("oops", response=mock.Mock(status_code=500))
        with mock.patch("pywebpush.webpush", side_effect=exc500):
            self.assertEqual(push._send(sub, {"title": "x"}), "error")

    def test_vapid_key_generator_produces_a_usable_pair(self):
        from io import StringIO
        from django.core.management import call_command
        from py_vapid import Vapid
        out = StringIO()
        call_command("generate_vapid_keys", stdout=out)
        text = out.getvalue()
        priv = [l for l in text.splitlines() if l.startswith("VAPID_PRIVATE_KEY=")][0].split("=", 1)[1]
        pub = [l for l in text.splitlines() if l.startswith("VAPID_PUBLIC_KEY=")][0].split("=", 1)[1]
        Vapid.from_string(priv)                       # parses: pywebpush will accept it
        self.assertEqual(len(pub), 87)                # 65-byte uncompressed P-256 point, base64url


class DealAlertTests(GeoWorld):
    def at(self, hour):
        return timezone.make_aware(datetime(2026, 11, 5, hour, 0))

    def opt_in(self):
        NotificationPreference.objects.update_or_create(user=self.user, defaults={"deal_alerts_enabled": True})

    def test_nothing_is_sent_without_opt_in(self):
        self.assertEqual(alerts.send_nearby_deal_alerts(self.at(10)), 0)
        self.assertFalse(Notification.objects.filter(user=self.user).exists())

    def test_opted_in_member_gets_one_nearby_deal(self):
        self.opt_in()
        self.assertEqual(alerts.send_nearby_deal_alerts(self.at(10)), 1)
        n = Notification.objects.get(user=self.user, category=NotificationCategory.OFFER)
        self.assertIn("Near soap", n.message)
        self.assertNotIn("Far soap", n.message)
        self.assertEqual(n.metadata["_channels"], ["in_app", "push"])

    def test_quiet_hours(self):
        self.opt_in()
        self.assertEqual(alerts.send_nearby_deal_alerts(self.at(22)), 0)
        self.assertEqual(alerts.send_nearby_deal_alerts(self.at(5)), 0)

    def test_at_most_one_a_day_and_never_the_same_offer_twice(self):
        self.opt_in()
        now = self.at(10)
        self.assertEqual(alerts.send_nearby_deal_alerts(now), 1)
        self.assertEqual(alerts.send_nearby_deal_alerts(now + timedelta(hours=2)), 0)       # same day
        second = self._offer(self.shop_a, self.kireka, "Second soap")
        self.assertEqual(alerts.send_nearby_deal_alerts(now + timedelta(days=1, hours=1)), 1)
        titles = " ".join(Notification.objects.filter(user=self.user).values_list("message", flat=True))
        self.assertIn("Near soap", titles)
        self.assertIn("Second soap", titles)                                                  # not a repeat of the first
        self.assertEqual(alerts.send_nearby_deal_alerts(now + timedelta(days=2, hours=1)), 0)  # nothing new left

    def test_no_alert_when_nothing_is_near(self):
        self.opt_in()
        Offer.objects.filter(pk=self.near.pk).update(status=Offer.Status.PAUSED)
        self.assertEqual(alerts.send_nearby_deal_alerts(self.at(10)), 0)


class CspAndMigrationTests(GeoWorld):
    def test_csp_allows_only_the_tile_host_for_images(self):
        r = self.client.get(reverse("landing"))
        csp = r["Content-Security-Policy"]
        self.assertIn("img-src 'self' data: blob: https://tile.openstreetmap.org", csp)
        self.assertIn("connect-src 'self'", csp)                    # geocoding/routing stay server-side
        self.assertNotIn("openstreetmap.org;", csp.split("script-src")[1].split(";")[0])

    @override_settings(MAP_TILE_URL="https://{s}.tiles.example.test/{z}/{x}/{y}.png")
    def test_subdomain_tile_templates_become_a_wildcard_host(self):
        from core.csp import tile_origin
        self.assertEqual(tile_origin(), "https://*.tiles.example.test")

    @override_settings(MAP_TILE_URL="http://insecure.example.test/{z}/{x}/{y}.png")
    def test_insecure_tile_hosts_are_not_added(self):
        from core.csp import tile_origin
        self.assertEqual(tile_origin(), "")

    def test_launch_areas_have_centres_after_migration(self):
        # The data migration only fills NULLs; it must never overwrite an admin's value.
        from importlib import import_module
        mod = import_module("core.migrations.0005_area_coordinates")
        Area.objects.create(name="Wakiso", latitude=1.0, longitude=2.0)
        from django.apps import apps as real_apps
        mod.fill_centres(real_apps, None)
        self.assertEqual(Area.objects.get(name="Wakiso").latitude, Decimal("1.000000"))
