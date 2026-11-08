from datetime import timedelta
from decimal import Decimal
from unittest.mock import Mock, patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import Role, User
from core.models import Area
from merchants.models import Merchant
from offers.models import Offer, OfferCategory
from payments.models import Payment
from payments.services.payment_flow import PaymentError, initiate_promotion_payment, process_collection_callback
from promotions.models import PromotionPackage, PromotionPurchase
from promotions.services import PromotionError, activate_purchase, create_pending_purchase, expire_stale_promotions

AUTH_RESPONSE = Mock(status_code=200, json=lambda: {"access_token": "tok", "expires_in": 300})


def dispatched_post(collect_response):
    def _post(url, *args, **kwargs):
        if url == "https://id.iotec.io/connect/token":
            return AUTH_RESPONSE
        return collect_response

    return _post


class PromotionServiceTests(TestCase):
    def setUp(self):
        self.area = Area.objects.create(name="Testville")
        self.category = OfferCategory.objects.create(key="soap", label="Soap")
        m_user = User.objects.create_user(phone="+256704000000", password="pass12345", role=Role.MERCHANT)
        self.merchant = Merchant.objects.create(
            user=m_user, business_name="Shop", category=self.category, area=self.area,
            status=Merchant.Status.VERIFIED,
        )
        self.offer = Offer.objects.create(
            merchant=self.merchant, category=self.category, area=self.area, item_name="Soap",
            normal_price=3000, member_price=2500, quantity=5,
            expires_at=timezone.now() + timedelta(days=1), status=Offer.Status.ACTIVE,
        )
        self.package = PromotionPackage.objects.create(
            code="boost-7d", label="7-day boost", price=5000, duration_days=7, visibility_boost=10,
        )

    def test_create_pending_purchase(self):
        purchase = create_pending_purchase(self.merchant, self.offer.id, self.package)
        self.assertEqual(purchase.status, PromotionPurchase.Status.PENDING)

    def test_cannot_double_pending_purchase_same_offer(self):
        create_pending_purchase(self.merchant, self.offer.id, self.package)
        with self.assertRaises(PromotionError):
            create_pending_purchase(self.merchant, self.offer.id, self.package)

    def test_cannot_promote_another_merchants_offer(self):
        other_user = User.objects.create_user(phone="+256704000001", password="pass12345", role=Role.MERCHANT)
        other_merchant = Merchant.objects.create(
            user=other_user, business_name="Other", category=self.category, area=self.area,
            status=Merchant.Status.VERIFIED,
        )
        with self.assertRaises(PromotionError):
            create_pending_purchase(other_merchant, self.offer.id, self.package)

    def test_activate_boosts_visibility_score(self):
        purchase = create_pending_purchase(self.merchant, self.offer.id, self.package)
        activate_purchase(purchase)
        self.offer.refresh_from_db()
        self.assertEqual(self.offer.visibility_score, 10)
        purchase.refresh_from_db()
        self.assertEqual(purchase.status, PromotionPurchase.Status.ACTIVE)
        self.assertIsNotNone(purchase.expires_at)

    def test_expire_reverts_visibility_boost(self):
        purchase = create_pending_purchase(self.merchant, self.offer.id, self.package)
        activate_purchase(purchase)
        PromotionPurchase.objects.filter(pk=purchase.pk).update(expires_at=timezone.now() - timedelta(days=1))
        count = expire_stale_promotions()
        self.assertEqual(count, 1)
        self.offer.refresh_from_db()
        self.assertEqual(self.offer.visibility_score, 0)

    def test_activate_is_idempotent(self):
        purchase = create_pending_purchase(self.merchant, self.offer.id, self.package)
        activate_purchase(purchase)
        activate_purchase(purchase)
        self.offer.refresh_from_db()
        self.assertEqual(self.offer.visibility_score, 10)  # not double-boosted


@override_settings(
    IOTEC_CLIENT_ID="test-id", IOTEC_CLIENT_SECRET="test-secret", IOTEC_WALLET_ID="wallet-123",
    IOTEC_BASE_URL="https://pay.iotec.io", IOTEC_TOKEN_URL="https://id.iotec.io/connect/token",
)
class PromotionPaymentFlowTests(TestCase):
    def setUp(self):
        cache.clear()
        self.area = Area.objects.create(name="Testville")
        self.category = OfferCategory.objects.create(key="soap", label="Soap")
        m_user = User.objects.create_user(phone="+256704010000", password="pass12345", role=Role.MERCHANT)
        self.merchant = Merchant.objects.create(
            user=m_user, business_name="Shop", category=self.category, area=self.area,
            status=Merchant.Status.VERIFIED,
        )
        self.offer = Offer.objects.create(
            merchant=self.merchant, category=self.category, area=self.area, item_name="Soap",
            normal_price=3000, member_price=2500, quantity=5,
            expires_at=timezone.now() + timedelta(days=1), status=Offer.Status.ACTIVE,
        )
        self.package = PromotionPackage.objects.create(
            code="boost-7d", label="7-day boost", price=5000, duration_days=7, visibility_boost=10,
        )

    @patch("requests.post")
    def test_full_promotion_payment_flow_boosts_offer(self, mock_post):
        mock_post.side_effect = dispatched_post(Mock(status_code=200, json=lambda: {"id": "txn-1", "status": "Pending"}))
        payment = initiate_promotion_payment(
            self.merchant, self.offer.id, self.package, Payment.Method.MOBILE_MONEY, payer_phone="+256704010000"
        )
        self.assertEqual(payment.purpose, Payment.Purpose.PROMOTION)
        self.assertEqual(payment.amount, self.package.price)

        process_collection_callback({"externalId": str(payment.internal_reference), "status": "Success"})

        self.offer.refresh_from_db()
        self.assertEqual(self.offer.visibility_score, 10)
        purchase = PromotionPurchase.objects.get(offer=self.offer)
        self.assertEqual(purchase.status, PromotionPurchase.Status.ACTIVE)

    @patch("requests.post")
    def test_failed_promotion_payment_does_not_boost(self, mock_post):
        mock_post.side_effect = dispatched_post(Mock(status_code=200, json=lambda: {"id": "txn-2", "status": "Pending"}))
        payment = initiate_promotion_payment(
            self.merchant, self.offer.id, self.package, Payment.Method.MOBILE_MONEY, payer_phone="+256704010000"
        )
        process_collection_callback({"externalId": str(payment.internal_reference), "status": "Failed"})
        self.offer.refresh_from_db()
        self.assertEqual(self.offer.visibility_score, 0)
        purchase = PromotionPurchase.objects.get(offer=self.offer)
        self.assertEqual(purchase.status, PromotionPurchase.Status.FAILED)


class PromotionAPITests(TestCase):
    def setUp(self):
        cache.clear()
        self.area = Area.objects.create(name="Testville")
        self.category = OfferCategory.objects.create(key="soap", label="Soap")
        m_user = User.objects.create_user(phone="+256704020000", password="pass12345", role=Role.MERCHANT)
        self.merchant = Merchant.objects.create(
            user=m_user, business_name="Shop", category=self.category, area=self.area,
            status=Merchant.Status.VERIFIED,
        )
        self.merchant_user = m_user
        self.offer = Offer.objects.create(
            merchant=self.merchant, category=self.category, area=self.area, item_name="Soap",
            normal_price=3000, member_price=2500, quantity=5,
            expires_at=timezone.now() + timedelta(days=1), status=Offer.Status.ACTIVE,
        )
        self.package = PromotionPackage.objects.create(
            code="boost-7d", label="7-day boost", price=5000, duration_days=7, visibility_boost=10,
        )

    def test_list_packages(self):
        self.client.force_login(self.merchant_user)
        resp = self.client.get(reverse("promotions:packages"))
        self.assertEqual(len(resp.json()["data"]), 1)

    @override_settings(
        IOTEC_CLIENT_ID="test-id", IOTEC_CLIENT_SECRET="test-secret", IOTEC_WALLET_ID="wallet-123",
        IOTEC_BASE_URL="https://pay.iotec.io", IOTEC_TOKEN_URL="https://id.iotec.io/connect/token",
    )
    @patch("requests.post")
    def test_purchase_promotion_via_api(self, mock_post):
        mock_post.side_effect = dispatched_post(Mock(status_code=200, json=lambda: {"id": "txn-1", "status": "Pending"}))
        self.client.force_login(self.merchant_user)
        resp = self.client.post(
            reverse("promotions:purchase_promotion"),
            {"offer_id": self.offer.id, "package_id": self.package.id, "method": "mobile_money", "phone": "+256704020000"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 201)

    def test_non_merchant_forbidden(self):
        member_user = User.objects.create_user(phone="+256704020001", password="pass12345", role=Role.MEMBER)
        self.client.force_login(member_user)
        resp = self.client.get(reverse("promotions:packages"))
        self.assertEqual(resp.status_code, 403)
