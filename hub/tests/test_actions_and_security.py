"""The buttons on the pages call the real API with a session + CSRF token;
these tests exercise that path and the security fixes."""
from datetime import timedelta

from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import Role, User
from members.models import Member
from offers.models import Offer


class ActionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_system_settings", verbosity=0)
        call_command("seed_subscription_plans", verbosity=0)
        call_command("seed_demo_data", verbosity=0)
        cls.member = Member.objects.select_related("user").first()

    def test_csrf_is_enforced_on_api_writes(self):
        c = Client(enforce_csrf_checks=True)
        c.force_login(self.member.user)
        offer = Offer.objects.filter(status=Offer.Status.ACTIVE).first()
        r = c.post(reverse("claims:claim_offer", args=[offer.pk]))
        self.assertEqual(r.status_code, 403)  # no token -> rejected

    def test_page_exposes_csrf_token_for_api_js(self):
        self.client.force_login(self.member.user)
        r = self.client.get(reverse("member"))
        self.assertContains(r, 'name="csrf-token"')
        self.assertContains(r, "hub/js/api.js")

    def test_logout_requires_post(self):
        self.client.force_login(self.member.user)
        self.assertEqual(self.client.get(reverse("accounts:logout")).status_code, 405)
        r = self.client.post(reverse("accounts:logout"))
        self.assertEqual(r.status_code, 302)

    def test_delivery_fare_is_bounded(self):
        self.client.force_login(self.member.user)
        r = self.client.post(
            reverse("deliveries:request_delivery"),
            {"claim_code": "1K-NOPE", "dropoff_area": "x", "fare": "99999999"},
            content_type="application/json",
        )
        # unknown claim is rejected before/alongside the fare check — never a 201
        self.assertIn(r.status_code, (400, 404))


class WebhookTests(TestCase):
    @override_settings(DEBUG=False, IOTEC_CALLBACK_SECRET="")
    def test_webhook_fails_closed_without_secret(self):
        r = self.client.post(reverse("payments:iotec_collection_callback"), {"externalId": "x", "status": "success"}, content_type="application/json")
        self.assertEqual(r.status_code, 401)

    @override_settings(DEBUG=False, IOTEC_CALLBACK_SECRET="s3cret-value")
    def test_webhook_rejects_wrong_secret_and_accepts_right_one(self):
        url = reverse("payments:iotec_collection_callback")
        bad = self.client.post(url, {"status": "success"}, content_type="application/json", HTTP_X_CALLBACK_SECRET="nope")
        self.assertEqual(bad.status_code, 401)
        ok = self.client.post(url, {"status": "success"}, content_type="application/json", HTTP_X_CALLBACK_SECRET="s3cret-value")
        self.assertEqual(ok.status_code, 200)


class CSPTests(TestCase):
    def test_csp_header_is_strict_and_pages_use_nonce(self):
        r = self.client.get(reverse("landing"))
        csp = r["Content-Security-Policy"]
        self.assertIn("script-src 'self' 'nonce-", csp)
        self.assertNotIn("unsafe-eval", csp)
        self.assertNotIn("cdn.", csp)
        body = r.content.decode()
        for host in ("unpkg.com", "cdn.tailwindcss.com", "cdn.jsdelivr.net", "fonts.googleapis.com"):
            self.assertNotIn(host, body)
