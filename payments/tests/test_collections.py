from unittest.mock import Mock, patch

from django.core.cache import cache
from django.test import TestCase, override_settings

from accounts.models import Role, User
from core.models import Area
from members.models import Member
from payments.models import Payment
from payments.services.iotec_client import IotecPayError
from payments.services.iotec_collections import initiate_card_collection, initiate_mobile_money_collection
from subscriptions.models import SubscriptionPlan

AUTH_RESPONSE = Mock(status_code=200, json=lambda: {"access_token": "tok", "expires_in": 300})


def dispatched_post(auth_url, collect_response):
    """iotec_auth and iotec_client both call the *same* requests.post
    (they share one module object via `import requests`), so a single
    mock dispatching on URL is needed rather than two independent
    per-module patches, which would just overwrite each other."""

    def _post(url, *args, **kwargs):
        if url == auth_url:
            return AUTH_RESPONSE
        return collect_response

    return _post


@override_settings(
    IOTEC_CLIENT_ID="test-id", IOTEC_CLIENT_SECRET="test-secret", IOTEC_WALLET_ID="wallet-123",
    IOTEC_BASE_URL="https://pay.iotec.io", IOTEC_TOKEN_URL="https://id.iotec.io/connect/token",
)
class CollectionsTests(TestCase):
    def setUp(self):
        cache.clear()
        area = Area.objects.create(name="Testville")
        SubscriptionPlan.objects.create(code="1k-monthly", label="Monthly", price=1000, period_days=30)
        user = User.objects.create_user(phone="+256701000000", password="pass12345", role=Role.MEMBER)
        self.member = Member.objects.create(user=user, area=area)
        self.payment = Payment.objects.create(
            purpose=Payment.Purpose.SUBSCRIPTION, user=user, method=Payment.Method.MOBILE_MONEY,
            amount=1000, payer_phone="+256701000000",
        )

    @patch("requests.post")
    def test_mobile_money_collection_sends_correct_shape(self, mock_post):
        collect_response = Mock(status_code=200, json=lambda: {"id": "txn-1", "status": "Pending"})
        mock_post.side_effect = dispatched_post("https://id.iotec.io/connect/token", collect_response)

        data = initiate_mobile_money_collection(self.payment)

        self.assertEqual(data["id"], "txn-1")
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.PENDING)
        self.assertEqual(self.payment.provider_transaction_id, "txn-1")

        collect_call = [c for c in mock_post.call_args_list if c.args[0].endswith("/collections/collect")][0]
        self.assertEqual(collect_call.args[0], "https://pay.iotec.io/api/collections/collect")
        body = collect_call.kwargs["json"]
        self.assertEqual(body["category"], "MobileMoney")
        self.assertEqual(body["walletId"], "wallet-123")
        self.assertEqual(body["externalId"], str(self.payment.internal_reference))
        self.assertEqual(body["payer"], "256701000000")          # spec: MSISDN as 256XXXXXXXXX or 0XXXXXXXXX
        self.assertEqual(body["amount"], float(self.payment.amount))   # required by the API
        self.assertEqual(collect_call.kwargs["headers"]["Authorization"], "Bearer tok")

    @patch("requests.post")
    def test_card_collection_captures_redirect_url(self, mock_post):
        collect_response = Mock(
            status_code=200,
            json=lambda: {"id": "txn-2", "status": "Pending", "cardRedirectUrl": "https://pay.iotec.io/checkout/abc"},
        )
        mock_post.side_effect = dispatched_post("https://id.iotec.io/connect/token", collect_response)

        card_payment = Payment.objects.create(
            purpose=Payment.Purpose.SUBSCRIPTION, user=self.member.user, method=Payment.Method.CARD,
            amount=1000, payer_email="member@example.com",
        )
        initiate_card_collection(card_payment)
        card_payment.refresh_from_db()
        self.assertEqual(card_payment.redirect_url, "https://pay.iotec.io/checkout/abc")
        self.assertEqual(card_payment.status, Payment.Status.PENDING)

    @patch("requests.post")
    def test_provider_error_raises_iotec_pay_error(self, mock_post):
        collect_response = Mock(status_code=400, json=lambda: {"message": "Invalid wallet"})
        mock_post.side_effect = dispatched_post("https://id.iotec.io/connect/token", collect_response)

        with self.assertRaises(IotecPayError):
            initiate_mobile_money_collection(self.payment)
        self.payment.refresh_from_db()
        # Status untouched by the client itself — the orchestration layer
        # (payment_flow.initiate_subscription_payment) is what marks it
        # FAILED, since the client only knows about the HTTP call.
        self.assertEqual(self.payment.status, Payment.Status.CREATED)
