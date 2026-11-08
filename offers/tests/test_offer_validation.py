from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from accounts.models import Role, User
from core.models import Area
from merchants.models import Merchant
from offers.models import Offer, OfferCategory


class OfferValidationTests(TestCase):
    def setUp(self):
        self.area = Area.objects.create(name="Testville")
        self.category = OfferCategory.objects.create(key="soap", label="Soap")
        merchant_user = User.objects.create_user(
            phone="+256700900000", password="pass12345", role=Role.MERCHANT
        )
        self.merchant = Merchant.objects.create(
            user=merchant_user, business_name="Test Shop", category=self.category, area=self.area
        )

    def _offer(self, **overrides):
        defaults = dict(
            merchant=self.merchant,
            category=self.category,
            area=self.area,
            item_name="Soap bar",
            normal_price=3000,
            member_price=2500,
            quantity=10,
            expires_at=timezone.now() + timedelta(days=1),
        )
        defaults.update(overrides)
        return Offer(**defaults)

    def test_valid_offer_saves(self):
        offer = self._offer()
        offer.save()
        self.assertEqual(offer.possible_saving, 500)
        self.assertFalse(offer.is_expired)

    def test_member_price_above_normal_rejected(self):
        offer = self._offer(member_price=3500)
        with self.assertRaises(ValidationError):
            offer.save()

    def test_negative_quantity_rejected(self):
        offer = self._offer(quantity=-1)
        with self.assertRaises(ValidationError):
            offer.save()

    def test_past_expiry_rejected(self):
        offer = self._offer(expires_at=timezone.now() - timedelta(days=1))
        with self.assertRaises(ValidationError):
            offer.save()
