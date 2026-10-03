from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from accounts.models import Role, User
from agents.models import Agent, AgentEarning
from agents.services import AgentError, verify_merchant, verify_rider
from core.models import Area, SystemSetting
from merchants.models import Merchant
from offers.models import OfferCategory
from riders.models import Rider


class AgentVerificationTests(TestCase):
    def setUp(self):
        SystemSetting.objects.update_or_create(key="agent.merchant_verification_fee_ugx", defaults={"value": "500"})
        SystemSetting.objects.update_or_create(key="agent.rider_verification_fee_ugx", defaults={"value": "300"})

        self.area_a = Area.objects.create(name="AreaA")
        self.area_b = Area.objects.create(name="AreaB")
        self.category = OfferCategory.objects.create(key="soap", label="Soap")

        agent_user = User.objects.create_user(phone="+256701400000", password="pass12345", role=Role.AGENT)
        self.agent = Agent.objects.create(user=agent_user)
        self.agent.areas.add(self.area_a)

        m_user = User.objects.create_user(phone="+256701400001", password="pass12345", role=Role.MERCHANT)
        self.merchant_in_area = Merchant.objects.create(
            user=m_user, business_name="Shop A", category=self.category, area=self.area_a
        )
        m_user2 = User.objects.create_user(phone="+256701400002", password="pass12345", role=Role.MERCHANT)
        self.merchant_outside_area = Merchant.objects.create(
            user=m_user2, business_name="Shop B", category=self.category, area=self.area_b
        )

        r_user = User.objects.create_user(phone="+256701400003", password="pass12345", role=Role.RIDER)
        self.rider_in_area = Rider.objects.create(user=r_user, area=self.area_a)

    def test_verify_merchant_in_agents_area_succeeds_and_credits_earning(self):
        merchant = verify_merchant(self.agent, self.merchant_in_area.id, "verified", {"real_person_met": True})
        self.assertEqual(merchant.status, Merchant.Status.VERIFIED)
        self.assertEqual(merchant.verified_by, self.agent.user)
        earning = AgentEarning.objects.get(agent=self.agent)
        self.assertEqual(earning.amount, Decimal("500"))

    def test_verify_merchant_outside_agents_area_rejected(self):
        with self.assertRaises(AgentError):
            verify_merchant(self.agent, self.merchant_outside_area.id, "verified", {})

    def test_rejected_outcome_does_not_credit_earning(self):
        verify_merchant(self.agent, self.merchant_in_area.id, "rejected", {"duplicate_account_check_passed": False})
        self.assertFalse(AgentEarning.objects.filter(agent=self.agent).exists())

    def test_verify_rider_credits_correct_fee(self):
        verify_rider(self.agent, self.rider_in_area.id, "verified", {})
        earning = AgentEarning.objects.get(agent=self.agent, source=AgentEarning.Source.RIDER_VERIFICATION)
        self.assertEqual(earning.amount, Decimal("300"))

    def test_invalid_outcome_rejected(self):
        with self.assertRaises(AgentError):
            verify_merchant(self.agent, self.merchant_in_area.id, "not_a_real_status", {})


class AgentAPITests(TestCase):
    def setUp(self):
        self.area = Area.objects.create(name="AreaA")
        self.category = OfferCategory.objects.create(key="soap", label="Soap")
        agent_user = User.objects.create_user(phone="+256701410000", password="pass12345", role=Role.AGENT)
        self.agent = Agent.objects.create(user=agent_user)
        self.agent.areas.add(self.area)
        self.agent_user = agent_user

        m_user = User.objects.create_user(phone="+256701410001", password="pass12345", role=Role.MERCHANT)
        self.merchant = Merchant.objects.create(user=m_user, business_name="Shop", category=self.category, area=self.area)

    def test_merchants_to_verify_scoped_to_agent_areas(self):
        self.client.force_login(self.agent_user)
        resp = self.client.get(reverse("agents:merchants_to_verify"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()["data"]), 1)

    def test_verify_merchant_via_api(self):
        self.client.force_login(self.agent_user)
        resp = self.client.post(
            reverse("agents:verify_merchant", args=[self.merchant.id]),
            {"outcome": "verified", "checklist": {"real_person_met": True}},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["data"]["status"], "verified")

    def test_non_agent_forbidden(self):
        member_user = User.objects.create_user(phone="+256701410002", password="pass12345", role=Role.MEMBER)
        self.client.force_login(member_user)
        resp = self.client.get(reverse("agents:merchants_to_verify"))
        self.assertEqual(resp.status_code, 403)

    def test_admin_agents_endpoint_requires_capability(self):
        # Plain agent (no capability, no superuser) cannot manage agents.
        self.client.force_login(self.agent_user)
        resp = self.client.get(reverse("agents:admin_agents"))
        self.assertEqual(resp.status_code, 403)

    def test_superuser_can_onboard_agent(self):
        super_user = User.objects.create_superuser(phone="+256701410099", password="pass12345")
        new_user = User.objects.create_user(phone="+256701410003", password="pass12345", role=Role.MEMBER)
        self.client.force_login(super_user)
        resp = self.client.post(
            reverse("agents:admin_agents"),
            {"user_id": str(new_user.id), "area_ids": [self.area.id]},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 201)
        new_user.refresh_from_db()
        self.assertEqual(new_user.role, Role.AGENT)
