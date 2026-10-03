"""Smoke tests: every hub page renders from the database for the right role,
is forbidden for the wrong one, and never leaks another user's data."""
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from accounts.models import Role, User
from agents.models import Agent
from core.models import Area
from members.models import Member
from merchants.models import Merchant
from riders.models import Rider

ADMIN_PAGES = [
    "admin_index", "admin_members", "admin_subscriptions", "admin_merchants", "admin_offers",
    "admin_claims", "admin_redemptions", "admin_riders", "admin_routes", "admin_pickup",
    "admin_agents", "admin_tasks", "admin_prices", "admin_payments", "admin_settlements",
    "admin_complaints", "admin_notifications", "admin_reports", "admin_settings",
]


class HubPageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_system_settings", verbosity=0)
        call_command("seed_subscription_plans", verbosity=0)
        call_command("seed_demo_data", verbosity=0)
        area = Area.objects.first()
        cls.admin = User.objects.create_user(phone="+256700000001", password="x", role=Role.ADMIN, first_name="Ada", last_name="Min")
        cls.admin.is_superuser = True
        cls.admin.save()
        cls.rider_user = User.objects.create_user(phone="+256700000002", password="x", role=Role.RIDER, first_name="Boda", last_name="Musoke")
        Rider.objects.create(user=cls.rider_user, area=area, status=Rider.Status.VERIFIED)
        cls.agent_user = User.objects.create_user(phone="+256700000003", password="x", role=Role.AGENT, first_name="Agent", last_name="One")
        agent = Agent.objects.create(user=cls.agent_user)
        agent.areas.add(area)
        cls.member = Member.objects.select_related("user").first()
        cls.merchant = Merchant.objects.select_related("user").first()

    def test_landing_is_public_and_database_backed(self):
        r = self.client.get(reverse("landing"))
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, "Kirombe Vendor Hub")  # old hard-coded mock seller

    def test_member_page(self):
        self.client.force_login(self.member.user)
        r = self.client.get(reverse("member"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, self.member.user.first_name)
        self.assertContains(r, self.member.referral_code)
        self.assertNotContains(r, "SARAH-1K")
        # search params must not break the page
        for qs in ("?q=sugar", "?cat=pharmacy&sort=cheapest", "?delivery=1&here=1", "?q=" + "a" * 500, "?sort=DROP"):
            self.assertEqual(self.client.get(reverse("member") + qs).status_code, 200, qs)

    def test_merchant_page(self):
        self.client.force_login(self.merchant.user)
        r = self.client.get(reverse("merchant"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, self.merchant.business_name)

    def test_rider_and_agent_pages(self):
        self.client.force_login(self.rider_user)
        self.assertEqual(self.client.get(reverse("rider")).status_code, 200)
        self.client.force_login(self.agent_user)
        self.assertEqual(self.client.get(reverse("agent")).status_code, 200)

    def test_all_admin_pages_render(self):
        self.client.force_login(self.admin)
        for name in ADMIN_PAGES:
            with self.subTest(page=name):
                r = self.client.get(reverse(name))
                self.assertEqual(r.status_code, 200, name)

    def test_admin_page_filters(self):
        self.client.force_login(self.admin)
        for name in ("admin_members", "admin_merchants", "admin_offers", "admin_claims", "admin_riders", "admin_complaints"):
            self.assertEqual(self.client.get(reverse(name) + "?q=a&status=active&page=999").status_code, 200, name)

    def test_role_isolation(self):
        self.client.force_login(self.member.user)
        for name in ("merchant", "rider", "agent", "admin_index", "admin_members"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 403, name)

    def test_anonymous_redirected_to_login(self):
        for name in ("member", "merchant", "rider", "agent", "admin_index"):
            r = self.client.get(reverse(name))
            self.assertEqual(r.status_code, 302, name)
            self.assertIn("/accounts/login/", r["Location"])

    def test_merchant_never_sees_full_unredeemed_claim_code(self):
        self.client.force_login(self.merchant.user)
        r = self.client.get(reverse("merchant"))
        for c in r.context["claims"]:
            if c["status"] != "redeemed":
                self.assertIn("•", c["code"])
