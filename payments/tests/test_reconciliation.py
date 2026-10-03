from datetime import timedelta
from unittest.mock import Mock, patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.models import Role, User
from core.models import Area, SystemSetting
from members.models import Member
from payments.models import Payment
from payments.services.payment_flow import initiate_subscription_payment
from payments.services.reconciliation import reconcile_all_pending_payments, reconcile_payment
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
)
class ReconciliationTests(TestCase):
    def setUp(self):
        cache.clear()
        SystemSetting.objects.update_or_create(
            key="payment.reconciliation_timeout_minutes", defaults={"value": "60"}
        )
        area = Area.objects.create(name="Testville")
        SubscriptionPlan.objects.create(code="1k-monthly", label="Monthly", price=1000, period_days=30)
        user = User.objects.create_user(phone="+256701300000", password="pass12345", role=Role.MEMBER)
        self.member = Member.objects.create(user=user, area=area)

    @patch("requests.get")
    @patch("requests.post")
    def test_reconciliation_resolves_stuck_success(self, mock_post, mock_get):
        mock_post.side_effect = dispatched_post(Mock(status_code=200, json=lambda: {"id": "txn-1", "status": "Pending"}))
        payment = initiate_subscription_payment(self.member, Payment.Method.MOBILE_MONEY, payer_phone="+256701300000")

        mock_get.return_value = Mock(status_code=200, json=lambda: {"status": "Success"})
        reconcile_payment(payment)

        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.SUCCESS)
        subscription = Subscription.objects.get(member=self.member)
        self.assertEqual(subscription.status, Subscription.Status.ACTIVE)

    @patch("requests.get")
    @patch("requests.post")
    def test_still_pending_within_timeout_stays_pending(self, mock_post, mock_get):
        mock_post.side_effect = dispatched_post(Mock(status_code=200, json=lambda: {"id": "txn-2", "status": "Pending"}))
        payment = initiate_subscription_payment(self.member, Payment.Method.MOBILE_MONEY, payer_phone="+256701300000")

        mock_get.return_value = Mock(status_code=200, json=lambda: {"status": "Pending"})
        reconcile_payment(payment)

        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.PENDING)

    @patch("requests.get")
    @patch("requests.post")
    def test_stuck_past_timeout_flagged_for_review(self, mock_post, mock_get):
        mock_post.side_effect = dispatched_post(Mock(status_code=200, json=lambda: {"id": "txn-3", "status": "Pending"}))
        payment = initiate_subscription_payment(self.member, Payment.Method.MOBILE_MONEY, payer_phone="+256701300000")
        Payment.objects.filter(pk=payment.pk).update(created_at=timezone.now() - timedelta(minutes=90))
        payment.refresh_from_db()

        mock_get.return_value = Mock(status_code=200, json=lambda: {"status": "Pending"})
        reconcile_payment(payment)

        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.REQUIRES_REVIEW)

    @patch("requests.get")
    @patch("requests.post")
    def test_provider_error_during_reconciliation_does_not_crash(self, mock_post, mock_get):
        mock_post.side_effect = dispatched_post(Mock(status_code=200, json=lambda: {"id": "txn-4", "status": "Pending"}))
        payment = initiate_subscription_payment(self.member, Payment.Method.MOBILE_MONEY, payer_phone="+256701300000")

        mock_get.return_value = Mock(status_code=500, json=lambda: {})
        # Should not raise.
        reconcile_payment(payment)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.PENDING)

    @patch("requests.get")
    @patch("requests.post")
    def test_reconcile_all_pending_summarizes_correctly(self, mock_post, mock_get):
        mock_post.side_effect = dispatched_post(Mock(status_code=200, json=lambda: {"id": "txn-5", "status": "Pending"}))
        initiate_subscription_payment(self.member, Payment.Method.MOBILE_MONEY, payer_phone="+256701300000")

        mock_get.return_value = Mock(status_code=200, json=lambda: {"status": "Success"})
        results = reconcile_all_pending_payments()
        self.assertEqual(results["checked"], 1)
        self.assertEqual(results["resolved"], 1)
