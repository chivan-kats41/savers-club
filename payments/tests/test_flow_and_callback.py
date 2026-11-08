from unittest.mock import Mock, patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import Role, User
from core.models import Area
from members.models import Member
from payments.models import LedgerEntry, Payment
from payments.services.payment_flow import PaymentError, initiate_subscription_payment, process_collection_callback
from subscriptions.models import Subscription, SubscriptionPlan

AUTH_RESPONSE = Mock(status_code=200, json=lambda: {"access_token": "tok", "expires_in": 300})


def dispatched_post(collect_response):
    def _post(url, *args, **kwargs):
        if url == "https://id.iotec.io/connect/token":
            return AUTH_RESPONSE
        return collect_response

    return _post


@override_settings(
    IOTEC_CLIENT_ID="test-id", IOTEC_CLIENT_SECRET="test-secret", IOTEC_WALLET_ID="wallet-123",
    IOTEC_BASE_URL="https://pay.iotec.io", IOTEC_TOKEN_URL="https://id.iotec.io/connect/token",
    IOTEC_CALLBACK_SECRET="shhh",
)
class PaymentFlowEndToEndTests(TestCase):
    def setUp(self):
        cache.clear()
        self.area = Area.objects.create(name="Testville")
        self.plan = SubscriptionPlan.objects.create(code="1k-monthly", label="Monthly", price=1000, period_days=30)
        self.user = User.objects.create_user(phone="+256701100000", password="pass12345", role=Role.MEMBER)
        self.member = Member.objects.create(user=self.user, area=self.area)

    @patch("requests.post")
    def test_full_mobile_money_flow_activates_subscription(self, mock_post):
        mock_post.side_effect = dispatched_post(Mock(status_code=200, json=lambda: {"id": "txn-1", "status": "Pending"}))

        payment = initiate_subscription_payment(self.member, Payment.Method.MOBILE_MONEY, payer_phone="+256701100000")
        self.assertEqual(payment.status, Payment.Status.PENDING)

        subscription = Subscription.objects.get(member=self.member)
        self.assertEqual(subscription.status, Subscription.Status.PENDING)

        process_collection_callback(
            {"externalId": str(payment.internal_reference), "status": "Success", "transactionId": "txn-1"}
        )

        payment.refresh_from_db()
        subscription.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.SUCCESS)
        self.assertEqual(subscription.status, Subscription.Status.ACTIVE)
        self.assertIsNotNone(subscription.current_period_end)
        self.assertTrue(LedgerEntry.objects.filter(payment=payment, direction=LedgerEntry.Direction.CREDIT).exists())

    @patch("requests.post")
    def test_failed_callback_does_not_activate(self, mock_post):
        mock_post.side_effect = dispatched_post(Mock(status_code=200, json=lambda: {"id": "txn-2", "status": "Pending"}))
        payment = initiate_subscription_payment(self.member, Payment.Method.MOBILE_MONEY, payer_phone="+256701100000")

        process_collection_callback({"externalId": str(payment.internal_reference), "status": "Failed"})

        payment.refresh_from_db()
        subscription = Subscription.objects.get(member=self.member)
        self.assertEqual(payment.status, Payment.Status.FAILED)
        self.assertEqual(subscription.status, Subscription.Status.PENDING)

    @patch("requests.post")
    def test_duplicate_success_callback_does_not_double_credit(self, mock_post):
        mock_post.side_effect = dispatched_post(Mock(status_code=200, json=lambda: {"id": "txn-3", "status": "Pending"}))
        payment = initiate_subscription_payment(self.member, Payment.Method.MOBILE_MONEY, payer_phone="+256701100000")

        process_collection_callback({"externalId": str(payment.internal_reference), "status": "Success"})
        process_collection_callback({"externalId": str(payment.internal_reference), "status": "Success"})

        self.assertEqual(LedgerEntry.objects.filter(payment=payment).count(), 1)

    @patch("requests.post")
    def test_missing_phone_for_mobile_money_rejected(self, mock_post):
        with self.assertRaises(PaymentError):
            initiate_subscription_payment(self.member, Payment.Method.MOBILE_MONEY, payer_phone="")
        mock_post.assert_not_called()

    def test_unknown_external_id_callback_logged_but_safe(self):
        result = process_collection_callback({"externalId": "not-a-real-uuid", "status": "Success"})
        self.assertIsNone(result)

    @patch("requests.post")
    def test_sent_to_vendor_then_duplicate_sent_to_vendor_is_a_noop(self, mock_post):
        from payments.models import PaymentCallback

        mock_post.side_effect = dispatched_post(Mock(status_code=200, json=lambda: {"id": "txn-9", "status": "Pending"}))
        payment = initiate_subscription_payment(self.member, Payment.Method.MOBILE_MONEY, payer_phone="+256701100000")

        payload = {"externalId": str(payment.internal_reference), "status": "SentToVendor", "transactionId": "txn-9"}
        process_collection_callback(payload)
        process_collection_callback(payload)

        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.SENT_TO_VENDOR)
        # Both callbacks logged for audit, but the second is marked as a
        # detected duplicate rather than reprocessed.
        callbacks = PaymentCallback.objects.filter(payment=payment).order_by("created_at")
        self.assertEqual(callbacks.count(), 2)
        self.assertIn("Duplicate event", callbacks.last().processing_notes)


@override_settings(IOTEC_CALLBACK_SECRET="shhh")
class CallbackEndpointSecurityTests(TestCase):
    def test_missing_secret_header_rejected(self):
        resp = self.client.post(
            reverse("payments:iotec_collection_callback"),
            data={"externalId": "x", "status": "Success"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 401)

    def test_wrong_secret_header_rejected(self):
        resp = self.client.post(
            reverse("payments:iotec_collection_callback"),
            data={"externalId": "x", "status": "Success"},
            content_type="application/json",
            HTTP_X_CALLBACK_SECRET="wrong",
        )
        self.assertEqual(resp.status_code, 401)

    def test_correct_secret_header_accepted(self):
        resp = self.client.post(
            reverse("payments:iotec_collection_callback"),
            data={"externalId": "x", "status": "Success"},
            content_type="application/json",
            HTTP_X_CALLBACK_SECRET="shhh",
        )
        self.assertEqual(resp.status_code, 200)

    def test_no_auth_required_ie_not_blocked_by_login(self):
        # Anonymous, no session — this must NOT be gated behind login,
        # since ioTec (not a browser session) calls it.
        resp = self.client.post(
            reverse("payments:iotec_collection_callback"),
            data={"externalId": "x", "status": "Failed"},
            content_type="application/json",
            HTTP_X_CALLBACK_SECRET="shhh",
        )
        self.assertNotEqual(resp.status_code, 403)
