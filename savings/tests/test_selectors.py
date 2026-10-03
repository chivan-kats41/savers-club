from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from accounts.models import Role, User
from claims.services import claim_offer, redeem_claim
from core.models import Area
from members.models import Member
from merchants.models import Merchant
from offers.models import Offer, OfferCategory
from savings.selectors import confirmed_savings_total, possible_savings_total, savings_summary


class SavingsSelectorTests(TestCase):
    def setUp(self):
        self.area = Area.objects.create(name="Testville")
        self.category = OfferCategory.objects.create(key="soap", label="Soap")
        m_user = User.objects.create_user(phone="+256700980000", password="pass12345", role=Role.MERCHANT)
        self.merchant = Merchant.objects.create(
            user=m_user, business_name="Test Shop", category=self.category, area=self.area
        )
        mem_user = User.objects.create_user(phone="+256700980001", password="pass12345", role=Role.MEMBER)
        self.member = Member.objects.create(user=mem_user, area=self.area)
        self.offer = Offer.objects.create(
            merchant=self.merchant, category=self.category, area=self.area, item_name="Soap",
            normal_price=3000, member_price=2500, quantity=5,
            expires_at=timezone.now() + timedelta(days=1), status=Offer.Status.ACTIVE,
        )

    def test_confirmed_savings_zero_before_redemption(self):
        self.assertEqual(confirmed_savings_total(self.member), 0)

    def test_confirmed_savings_after_redemption(self):
        claim = claim_offer(self.member, self.offer.id)
        redeem_claim(self.merchant, claim.code)
        self.assertEqual(confirmed_savings_total(self.member), 500)

    def test_possible_savings_reflects_active_offers(self):
        # 5 units at 500 saving each isn't summed by unit — possible
        # savings is per distinct active offer, not per unit of stock.
        self.assertEqual(possible_savings_total(self.member), 500)

    def test_summary_shape(self):
        summary = savings_summary(self.member)
        self.assertIn("confirmed_total", summary)
        self.assertIn("possible_total", summary)
        self.assertIn("claims_count", summary)
