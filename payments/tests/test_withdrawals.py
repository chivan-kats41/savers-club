from decimal import Decimal
from unittest.mock import Mock, patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from datetime import timedelta

from accounts.models import Role, User
from core.models import Area, SystemSetting
from deliveries.models import DeliveryJob, RiderEarning
from payments.models import LedgerEntry, Withdrawal
from payments.services.withdrawal_flow import (
    WithdrawalError,
    available_rider_balance,
    process_disbursement_callback,
    request_rider_withdrawal,
)
from riders.models import Rider

AUTH_RESPONSE = Mock(status_code=200, json=lambda: {"access_token": "tok", "expires_in": 300})


def dispatched_post(disburse_response):
    def _post(url, *args, **kwargs):
        if url == "https://id.iotec.io/connect/token":
            return AUTH_RESPONSE
        return disburse_response

    return _post


def _make_rider_with_earnings(net_amount=Decimal("10000")):
    area = Area.objects.create(name="Testville")
    user = User.objects.create_user(phone="+256701200000", password="pass12345", role=Role.RIDER)
    rider = Rider.objects.create(user=user, area=area, status=Rider.Status.VERIFIED)

    from merchants.models import Merchant
    from offers.models import OfferCategory

    category = OfferCategory.objects.create(key="soap", label="Soap")
    m_user = User.objects.create_user(phone="+256701200001", password="pass12345", role=Role.MERCHANT)
    merchant = Merchant.objects.create(user=m_user, business_name="Shop", category=category, area=area)
    job = DeliveryJob.objects.create(
        pickup_merchant=merchant, dropoff_area=area, dropoff_address="x",
        fare=net_amount, status=DeliveryJob.Status.DELIVERED,
    )
    RiderEarning.objects.create(rider=rider, delivery_job=job, gross_amount=net_amount, commission_amount=0, net_amount=net_amount)
    return rider


class BalanceCalculationTests(TestCase):
    def test_available_balance_equals_earnings_when_no_withdrawals(self):
        rider = _make_rider_with_earnings(Decimal("10000"))
        self.assertEqual(available_rider_balance(rider), Decimal("10000"))

    def test_pending_withdrawal_reduces_available_balance(self):
        rider = _make_rider_with_earnings(Decimal("10000"))
        Withdrawal.objects.create(
            user=rider.user, source=Withdrawal.Source.RIDER_EARNINGS, amount=Decimal("4000"),
            fee=Decimal("40"), net_amount=Decimal("3960"), phone="+256701200000", status=Withdrawal.Status.PENDING,
        )
        self.assertEqual(available_rider_balance(rider), Decimal("6000"))

    def test_failed_withdrawal_does_not_reduce_balance(self):
        rider = _make_rider_with_earnings(Decimal("10000"))
        Withdrawal.objects.create(
            user=rider.user, source=Withdrawal.Source.RIDER_EARNINGS, amount=Decimal("4000"),
            fee=Decimal("40"), net_amount=Decimal("3960"), phone="+256701200000", status=Withdrawal.Status.FAILED,
        )
        self.assertEqual(available_rider_balance(rider), Decimal("10000"))


@override_settings(
    IOTEC_CLIENT_ID="test-id", IOTEC_CLIENT_SECRET="test-secret", IOTEC_WALLET_ID="wallet-123",
    IOTEC_BASE_URL="https://pay.iotec.io", IOTEC_TOKEN_URL="https://id.iotec.io/connect/token",
)
class WithdrawalRequestTests(TestCase):
    def setUp(self):
        cache.clear()
        SystemSetting.objects.update_or_create(key="withdrawal.minimum_ugx", defaults={"value": "2000"})
        SystemSetting.objects.update_or_create(key="withdrawal.fee_percent", defaults={"value": "1.00"})
        self.rider = _make_rider_with_earnings(Decimal("10000"))

    @patch("requests.post")
    def test_successful_withdrawal_request(self, mock_post):
        mock_post.side_effect = dispatched_post(Mock(status_code=200, json=lambda: {"id": "wd-1", "status": "SentToVendor"}))
        withdrawal = request_rider_withdrawal(self.rider, Decimal("5000"), "+256701200000")
        self.assertEqual(withdrawal.fee, Decimal("50.00"))
        self.assertEqual(withdrawal.net_amount, Decimal("4950.00"))
        self.assertEqual(withdrawal.status, Withdrawal.Status.PROCESSING)

    @patch("requests.post")
    def test_below_minimum_rejected(self, mock_post):
        with self.assertRaises(WithdrawalError):
            request_rider_withdrawal(self.rider, Decimal("500"), "+256701200000")
        mock_post.assert_not_called()

    @patch("requests.post")
    def test_exceeding_balance_rejected(self, mock_post):
        with self.assertRaises(WithdrawalError):
            request_rider_withdrawal(self.rider, Decimal("50000"), "+256701200000")
        mock_post.assert_not_called()

    @patch("requests.post")
    def test_second_withdrawal_cannot_exceed_remaining_balance(self, mock_post):
        mock_post.side_effect = dispatched_post(Mock(status_code=200, json=lambda: {"id": "wd-1", "status": "SentToVendor"}))
        request_rider_withdrawal(self.rider, Decimal("6000"), "+256701200000")
        with self.assertRaises(WithdrawalError):
            request_rider_withdrawal(self.rider, Decimal("5000"), "+256701200000")

    @patch("requests.post")
    def test_disbursement_success_callback_completes_and_ledgers(self, mock_post):
        mock_post.side_effect = dispatched_post(Mock(status_code=200, json=lambda: {"id": "wd-1", "status": "SentToVendor"}))
        withdrawal = request_rider_withdrawal(self.rider, Decimal("5000"), "+256701200000")

        process_disbursement_callback(
            {"externalId": str(withdrawal.internal_reference), "status": "Success", "transactionId": "wd-1"}
        )
        withdrawal.refresh_from_db()
        self.assertEqual(withdrawal.status, Withdrawal.Status.COMPLETED)
        self.assertIsNotNone(withdrawal.completed_at)
        self.assertTrue(LedgerEntry.objects.filter(reference=str(withdrawal.internal_reference), direction=LedgerEntry.Direction.DEBIT).exists())

    @patch("requests.post")
    def test_disbursement_failure_releases_reservation(self, mock_post):
        mock_post.side_effect = dispatched_post(Mock(status_code=200, json=lambda: {"id": "wd-1", "status": "SentToVendor"}))
        withdrawal = request_rider_withdrawal(self.rider, Decimal("5000"), "+256701200000")
        process_disbursement_callback({"externalId": str(withdrawal.internal_reference), "status": "Failed"})
        withdrawal.refresh_from_db()
        self.assertEqual(withdrawal.status, Withdrawal.Status.FAILED)
        # Balance should show the 5000 as available again.
        self.assertEqual(available_rider_balance(self.rider), Decimal("10000"))

    @patch("requests.post")
    def test_duplicate_disbursement_callback_does_not_double_ledger(self, mock_post):
        mock_post.side_effect = dispatched_post(Mock(status_code=200, json=lambda: {"id": "wd-1", "status": "SentToVendor"}))
        withdrawal = request_rider_withdrawal(self.rider, Decimal("5000"), "+256701200000")
        payload = {"externalId": str(withdrawal.internal_reference), "status": "Success", "transactionId": "wd-1"}
        process_disbursement_callback(payload)
        process_disbursement_callback(payload)
        self.assertEqual(LedgerEntry.objects.filter(reference=str(withdrawal.internal_reference)).count(), 1)
