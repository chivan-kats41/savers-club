from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Role, User
from claims.models import OfferClaim
from claims.services import ClaimError, cancel_claim, claim_offer, expire_stale_claims, redeem_claim
from core.models import Area
from members.models import Member
from merchants.models import Merchant
from offers.models import Offer, OfferCategory
from savings.models import SavingsRecord
from savings.selectors import confirmed_savings_total


def _make_offer(area, category, merchant, quantity=5, normal=3000, member_price=2500):
    return Offer.objects.create(
        merchant=merchant,
        category=category,
        area=area,
        item_name="Soap bar",
        normal_price=normal,
        member_price=member_price,
        quantity=quantity,
        expires_at=timezone.now() + timedelta(days=1),
        status=Offer.Status.ACTIVE,
    )


class ClaimServiceTests(TestCase):
    def setUp(self):
        self.area = Area.objects.create(name="Testville")
        self.category = OfferCategory.objects.create(key="soap", label="Soap")
        m_user = User.objects.create_user(phone="+256700950000", password="pass12345", role=Role.MERCHANT)
        self.merchant = Merchant.objects.create(
            user=m_user, business_name="Test Shop", category=self.category, area=self.area
        )
        mem_user = User.objects.create_user(phone="+256700950001", password="pass12345", role=Role.MEMBER)
        self.member = Member.objects.create(user=mem_user, area=self.area)
        self.offer = _make_offer(self.area, self.category, self.merchant)

    def test_claim_reserves_stock(self):
        claim_offer(self.member, self.offer.id)
        self.offer.refresh_from_db()
        self.assertEqual(self.offer.quantity, 4)

    def test_claim_code_locked_price_at_claim_time(self):
        claim = claim_offer(self.member, self.offer.id)
        self.assertEqual(claim.expected_saving, 500)

    def test_cannot_claim_out_of_stock_offer(self):
        self.offer.quantity = 0
        self.offer.save(update_fields=["quantity"])
        with self.assertRaises(ClaimError):
            claim_offer(self.member, self.offer.id)

    def test_cannot_double_claim_same_offer(self):
        claim_offer(self.member, self.offer.id)
        with self.assertRaises(ClaimError):
            claim_offer(self.member, self.offer.id)

    def test_redeem_creates_savings_record(self):
        claim = claim_offer(self.member, self.offer.id)
        redeem_claim(self.merchant, claim.code)
        self.assertTrue(SavingsRecord.objects.filter(claim=claim).exists())
        self.assertEqual(confirmed_savings_total(self.member), 500)

    def test_redeem_wrong_merchant_rejected(self):
        claim = claim_offer(self.member, self.offer.id)
        other_user = User.objects.create_user(phone="+256700950002", password="pass12345", role=Role.MERCHANT)
        other_merchant = Merchant.objects.create(
            user=other_user, business_name="Other Shop", category=self.category, area=self.area
        )
        with self.assertRaises(ClaimError):
            redeem_claim(other_merchant, claim.code)

    def test_double_redeem_rejected(self):
        claim = claim_offer(self.member, self.offer.id)
        redeem_claim(self.merchant, claim.code)
        with self.assertRaises(ClaimError):
            redeem_claim(self.merchant, claim.code)

    def test_invalid_code_rejected(self):
        with self.assertRaises(ClaimError):
            redeem_claim(self.merchant, "1K-ZZZZ")

    def test_cancel_restocks_offer(self):
        claim = claim_offer(self.member, self.offer.id)
        cancel_claim(self.member, claim.code)
        self.offer.refresh_from_db()
        self.assertEqual(self.offer.quantity, 5)
        claim.refresh_from_db()
        self.assertEqual(claim.status, OfferClaim.Status.CANCELLED)

    def test_expire_stale_claims_restocks(self):
        claim = claim_offer(self.member, self.offer.id)
        claim.expires_at = timezone.now() - timedelta(hours=1)
        claim.save(update_fields=["expires_at"])
        count = expire_stale_claims()
        self.assertEqual(count, 1)
        self.offer.refresh_from_db()
        self.assertEqual(self.offer.quantity, 5)


class ClaimAPITests(TestCase):
    def setUp(self):
        self.area = Area.objects.create(name="Testville")
        self.category = OfferCategory.objects.create(key="soap", label="Soap")
        m_user = User.objects.create_user(phone="+256700960000", password="pass12345", role=Role.MERCHANT)
        self.merchant = Merchant.objects.create(
            user=m_user, business_name="Test Shop", category=self.category, area=self.area
        )
        self.merchant_user = m_user
        mem_user = User.objects.create_user(phone="+256700960001", password="pass12345", role=Role.MEMBER)
        self.member = Member.objects.create(user=mem_user, area=self.area)
        self.member_user = mem_user
        self.offer = _make_offer(self.area, self.category, self.merchant)

    def test_member_claims_via_api(self):
        self.client.force_login(self.member_user)
        resp = self.client.post(reverse("claims:claim_offer", args=[self.offer.id]))
        self.assertEqual(resp.status_code, 201)
        self.assertIn("code", resp.json()["data"])

    def test_merchant_redeems_via_api(self):
        claim = claim_offer(self.member, self.offer.id)
        self.client.force_login(self.merchant_user)
        resp = self.client.post(reverse("claims:redeem_claim"), {"code": claim.code}, content_type="application/json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["data"]["status"], "redeemed")

    def test_merchant_cannot_see_other_merchants_claims(self):
        claim_offer(self.member, self.offer.id)
        other_user = User.objects.create_user(phone="+256700960002", password="pass12345", role=Role.MERCHANT)
        Merchant.objects.create(user=other_user, business_name="Other Shop", category=self.category, area=self.area)
        self.client.force_login(other_user)
        resp = self.client.get(reverse("claims:merchant_claims"))
        self.assertEqual(resp.json()["data"], [])

    def test_member_cannot_redeem(self):
        claim = claim_offer(self.member, self.offer.id)
        self.client.force_login(self.member_user)
        resp = self.client.post(reverse("claims:redeem_claim"), {"code": claim.code}, content_type="application/json")
        self.assertEqual(resp.status_code, 403)
