from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Role, User
from agents.models import Agent
from core.models import Area
from merchants.models import Merchant
from offers.merchant_services import OfferError, create_offer, delete_offer, update_offer
from offers.models import Offer, OfferCategory


class MerchantOfferServiceTests(TestCase):
    def setUp(self):
        self.area = Area.objects.create(name="Testville")
        self.category = OfferCategory.objects.create(key="soap", label="Soap")
        user = User.objects.create_user(phone="+256702000000", password="pass12345", role=Role.MERCHANT)
        self.merchant = Merchant.objects.create(
            user=user, business_name="Shop", category=self.category, area=self.area,
            status=Merchant.Status.VERIFIED,
        )
        self.unverified_user = User.objects.create_user(phone="+256702000001", password="pass12345", role=Role.MERCHANT)
        self.unverified_merchant = Merchant.objects.create(
            user=self.unverified_user, business_name="Shop2", category=self.category, area=self.area,
        )

    def _fields(self, **overrides):
        defaults = dict(
            category=self.category, area=self.area, item_name="Soap",
            normal_price=3000, member_price=2500, quantity=5,
            expires_at=timezone.now() + timedelta(days=1),
        )
        defaults.update(overrides)
        return defaults

    def test_verified_merchant_can_create_offer_pending(self):
        offer = create_offer(self.merchant, **self._fields())
        self.assertEqual(offer.status, Offer.Status.PENDING)

    def test_unverified_merchant_cannot_create_offer(self):
        with self.assertRaises(OfferError):
            create_offer(self.unverified_merchant, **self._fields())

    def test_update_active_offer_resets_to_pending(self):
        offer = create_offer(self.merchant, **self._fields())
        offer.status = Offer.Status.ACTIVE
        offer.save(update_fields=["status"])
        updated = update_offer(self.merchant, offer.id, item_name="New name")
        self.assertEqual(updated.status, Offer.Status.PENDING)

    def test_cannot_delete_offer_with_claims(self):
        from claims.services import claim_offer
        from members.models import Member

        offer = create_offer(self.merchant, **self._fields())
        offer.status = Offer.Status.ACTIVE
        offer.save(update_fields=["status"])
        mem_user = User.objects.create_user(phone="+256702000002", password="pass12345", role=Role.MEMBER)
        member = Member.objects.create(user=mem_user, area=self.area)
        claim_offer(member, offer.id)
        with self.assertRaises(OfferError):
            delete_offer(self.merchant, offer.id)

    def test_delete_offer_without_claims_succeeds(self):
        offer = create_offer(self.merchant, **self._fields())
        delete_offer(self.merchant, offer.id)
        self.assertFalse(Offer.objects.filter(pk=offer.id).exists())


class MerchantOfferAPITests(TestCase):
    def setUp(self):
        self.area = Area.objects.create(name="Testville")
        self.category = OfferCategory.objects.create(key="soap", label="Soap")
        user = User.objects.create_user(phone="+256702010000", password="pass12345", role=Role.MERCHANT)
        self.merchant = Merchant.objects.create(
            user=user, business_name="Shop", category=self.category, area=self.area,
            status=Merchant.Status.VERIFIED,
        )
        self.merchant_user = user

    def test_create_offer_via_api(self):
        self.client.force_login(self.merchant_user)
        resp = self.client.post(
            reverse("offers:merchant_offers"),
            {
                "category_id": self.category.id, "area_id": self.area.id, "item_name": "Soap",
                "normal_price": "3000", "member_price": "2500", "quantity": 5,
                "expires_at": (timezone.now() + timedelta(days=1)).isoformat(),
            },
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["data"]["status"], "pending")

    def test_merchant_only_sees_own_offers(self):
        other_user = User.objects.create_user(phone="+256702010001", password="pass12345", role=Role.MERCHANT)
        other_merchant = Merchant.objects.create(
            user=other_user, business_name="Other", category=self.category, area=self.area,
            status=Merchant.Status.VERIFIED,
        )
        Offer.objects.create(
            merchant=other_merchant, category=self.category, area=self.area, item_name="Other item",
            normal_price=1000, member_price=800, quantity=1,
            expires_at=timezone.now() + timedelta(days=1),
        )
        self.client.force_login(self.merchant_user)
        resp = self.client.get(reverse("offers:merchant_offers"))
        self.assertEqual(resp.json()["data"], [])

    def test_non_merchant_forbidden(self):
        member_user = User.objects.create_user(phone="+256702010002", password="pass12345", role=Role.MEMBER)
        self.client.force_login(member_user)
        resp = self.client.get(reverse("offers:merchant_offers"))
        self.assertEqual(resp.status_code, 403)


class AgentOfferApprovalTests(TestCase):
    def setUp(self):
        self.area = Area.objects.create(name="Testville")
        self.other_area = Area.objects.create(name="Elsewhere")
        self.category = OfferCategory.objects.create(key="soap", label="Soap")
        m_user = User.objects.create_user(phone="+256702020000", password="pass12345", role=Role.MERCHANT)
        self.merchant = Merchant.objects.create(
            user=m_user, business_name="Shop", category=self.category, area=self.area,
            status=Merchant.Status.VERIFIED,
        )
        self.offer = Offer.objects.create(
            merchant=self.merchant, category=self.category, area=self.area, item_name="Soap",
            normal_price=3000, member_price=2500, quantity=5,
            expires_at=timezone.now() + timedelta(days=1), status=Offer.Status.PENDING,
        )
        agent_user = User.objects.create_user(phone="+256702020001", password="pass12345", role=Role.AGENT)
        self.agent = Agent.objects.create(user=agent_user)
        self.agent.areas.add(self.area)
        self.agent_user = agent_user

    def test_agent_approves_offer_in_area(self):
        self.client.force_login(self.agent_user)
        resp = self.client.post(reverse("agents:approve_offer", args=[self.offer.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["data"]["status"], "active")

    def test_agent_cannot_approve_offer_outside_area(self):
        self.offer.area = self.other_area
        self.offer.save(update_fields=["area"])
        self.client.force_login(self.agent_user)
        resp = self.client.post(reverse("agents:approve_offer", args=[self.offer.id]))
        self.assertEqual(resp.status_code, 400)

    def test_agent_rejects_offer(self):
        self.client.force_login(self.agent_user)
        resp = self.client.post(reverse("agents:reject_offer", args=[self.offer.id]), {"reason": "Bad photos"}, content_type="application/json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["data"]["status"], "rejected")


class NearbyOffersAPITests(TestCase):
    def setUp(self):
        self.area = Area.objects.create(name="Testville")
        self.category = OfferCategory.objects.create(key="soap", label="Soap")
        m_user = User.objects.create_user(phone="+256702030000", password="pass12345", role=Role.MERCHANT)
        merchant = Merchant.objects.create(
            user=m_user, business_name="Shop", category=self.category, area=self.area,
            status=Merchant.Status.VERIFIED,
        )
        Offer.objects.create(
            merchant=merchant, category=self.category, area=self.area, item_name="Cheap soap",
            normal_price=3000, member_price=2500, quantity=5,
            expires_at=timezone.now() + timedelta(days=1), status=Offer.Status.ACTIVE,
        )
        Offer.objects.create(
            merchant=merchant, category=self.category, area=self.area, item_name="Pending soap",
            normal_price=3000, member_price=2500, quantity=5,
            expires_at=timezone.now() + timedelta(days=1), status=Offer.Status.PENDING,
        )
        mem_user = User.objects.create_user(phone="+256702030001", password="pass12345", role=Role.MEMBER)
        self.member_user = mem_user

    def test_nearby_only_shows_active_offers(self):
        self.client.force_login(self.member_user)
        resp = self.client.get(reverse("offers:nearby_offers"))
        data = resp.json()["data"]
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["item_name"], "Cheap soap")

    def test_search_filters_by_item_name(self):
        self.client.force_login(self.member_user)
        resp = self.client.get(reverse("offers:nearby_offers"), {"q": "nonexistent"})
        self.assertEqual(resp.json()["data"], [])
