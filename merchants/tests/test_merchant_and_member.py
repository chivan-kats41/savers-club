from django.test import TestCase

from accounts.models import Role, User
from core.models import Area
from merchants.models import Merchant
from offers.models import OfferCategory


class MerchantModelTests(TestCase):
    def test_merchant_defaults_to_pending(self):
        area = Area.objects.create(name="Testville")
        category = OfferCategory.objects.create(key="pharmacy", label="Pharmacy")
        user = User.objects.create_user(phone="+256700910000", password="pass12345", role=Role.MERCHANT)
        merchant = Merchant.objects.create(
            user=user, business_name="Test Pharmacy", category=category, area=area
        )
        self.assertEqual(merchant.status, Merchant.Status.PENDING)
        self.assertIsNone(merchant.verified_at)
