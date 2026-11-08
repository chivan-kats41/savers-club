"""A payment that stays "pending" for days: why it happened and the guard rails that now stop it.

Root cause in local development: ioTec's callback cannot reach 127.0.0.1 and nothing was running the background sweep, so
no code ever asked ioTec what became of the payment. Also, a payment parked as REQUIRES_REVIEW was never looked at again,
even if the customer approved late."""
from datetime import timedelta
from io import StringIO
from unittest.mock import Mock, patch

from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import Role, User
from core.models import Area, SystemSetting
from members.models import Member
from payments.models import Payment
from payments.services import reconciliation
from payments.services.iotec_client import IotecPayError
from payments.services.payment_flow import initiate_subscription_payment
from payments.services.reconciliation import reconcile_all_pending_payments, reconcile_payment
from subscriptions.models import Subscription, SubscriptionPayment, SubscriptionPlan

AUTH = Mock(status_code=200, json=lambda: {"access_token": "tok", "expires_in": 300})


def post_router(collect):
    return lambda url, *a, **k: AUTH if url == "https://id.iotec.io/connect/token" else collect


@override_settings(IOTEC_CLIENT_ID="id", IOTEC_CLIENT_SECRET="secret", IOTEC_WALLET_ID="wallet-123",
                   IOTEC_BASE_URL="https://pay.iotec.io", IOTEC_TOKEN_URL="https://id.iotec.io/connect/token")
class StuckPaymentTests(TestCase):
    def setUp(self):
        cache.clear()
        SystemSetting.objects.update_or_create(key="payment.reconciliation_timeout_minutes", defaults={"value": "60"})
        area = Area.objects.create(name="Testville")
        SubscriptionPlan.objects.create(code="1k-monthly", label="Monthly", price=1000, period_days=30)
        self.user = User.objects.create_user(phone="+256701400000", password="pass12345", role=Role.MEMBER)
        self.member = Member.objects.create(user=self.user, area=area)

    def make_payment(self, status=Payment.Status.SENT_TO_VENDOR, age_minutes=0):
        with patch("requests.post") as post:
            post.side_effect = post_router(Mock(status_code=200, json=lambda: {"id": "txn-1", "status": "SentToVendor"}))
            pay = initiate_subscription_payment(self.member, Payment.Method.MOBILE_MONEY, payer_phone="+256701400000")
        Payment.objects.filter(pk=pay.pk).update(status=status, created_at=timezone.now() - timedelta(minutes=age_minutes))
        pay.refresh_from_db()
        return pay

    def status_of(self, state, amount=None):
        body = {"status": state}
        if amount is not None:
            body.update(amount=amount, currency="UGX")
        return Mock(status_code=200, json=lambda: body)

    # ------------------------------------------------------------------ the sweep
    @patch("requests.get")
    def test_a_parked_payment_is_rechecked_and_a_late_success_still_activates_the_subscription(self, get):
        pay = self.make_payment(age_minutes=3 * 24 * 60)
        get.return_value = self.status_of("SentToVendor")         # ioTec still says "waiting for the customer"
        reconcile_payment(pay)                                   # ...past the timeout: parked for review
        pay.refresh_from_db(); self.assertEqual(pay.status, Payment.Status.REQUIRES_REVIEW)

        get.return_value = self.status_of("Success", 1000)       # the customer approved late
        reconcile_all_pending_payments()
        pay.refresh_from_db()
        self.assertEqual(pay.status, Payment.Status.SUCCESS)
        self.assertEqual(Subscription.objects.get(member=self.member).status, Subscription.Status.ACTIVE)
        self.assertEqual(SubscriptionPayment.objects.get().status, SubscriptionPayment.Status.SUCCESS)

    @patch("requests.get")
    def test_a_parked_payment_that_ioTec_reports_failed_releases_the_member(self, get):
        pay = self.make_payment(status=Payment.Status.REQUIRES_REVIEW, age_minutes=3 * 24 * 60)
        get.return_value = self.status_of("Failed")
        reconcile_all_pending_payments()
        pay.refresh_from_db()
        self.assertEqual(pay.status, Payment.Status.FAILED)
        self.assertEqual(SubscriptionPayment.objects.get().status, SubscriptionPayment.Status.FAILED)

    @patch("requests.get")
    def test_very_old_parked_payments_are_left_alone(self, get):
        self.make_payment(status=Payment.Status.REQUIRES_REVIEW, age_minutes=(reconciliation.REVIEW_RECHECK_DAYS + 1) * 24 * 60)
        res = reconcile_all_pending_payments()
        self.assertEqual(res["checked"], 0)
        get.assert_not_called()                                  # no endless polling of ancient payments

    @patch("requests.get")
    def test_amount_mismatch_stays_parked_and_is_not_reported_on_every_sweep(self, get):
        pay = self.make_payment(age_minutes=5)
        get.return_value = self.status_of("Success", 500)        # paid 500, we asked for 1000
        with patch("core.services.record_risk_event") as risk:
            reconcile_payment(pay)
            pay.refresh_from_db()
            self.assertEqual(pay.status, Payment.Status.REQUIRES_REVIEW)
            reconcile_all_pending_payments(); reconcile_all_pending_payments()
        self.assertEqual(risk.call_count, 1)                     # logged once, not every 5 minutes
        pay.refresh_from_db(); self.assertEqual(pay.status, Payment.Status.REQUIRES_REVIEW)   # never credited

    def test_unreachable_provider_is_reported_not_silently_ignored(self):
        pay = self.make_payment(age_minutes=5)
        with patch.object(reconciliation, "fetch_collection_state", side_effect=IotecPayError("auth failed")):
            reconcile_payment(pay)
        self.assertTrue(pay.provider_check_failed)
        pay.refresh_from_db(); self.assertEqual(pay.status, Payment.Status.SENT_TO_VENDOR)    # not guessed

    @patch("requests.get")
    def test_command_prints_what_it_found(self, get):
        pay = self.make_payment(age_minutes=2)
        get.return_value = self.status_of("Success", 1000)
        out = StringIO(); call_command("reconcile_payments", stdout=out)
        self.assertIn(f"payment #{pay.pk}", out.getvalue())
        self.assertIn("sent_to_vendor -> success", out.getvalue())

    def test_command_explains_provider_failures(self):
        self.make_payment(age_minutes=2)
        out = StringIO()
        with patch.object(reconciliation, "fetch_collection_state", side_effect=IotecPayError("401")):
            call_command("reconcile_payments", stdout=out)
        self.assertIn("could not reach/authenticate with ioTec", out.getvalue())

    # ------------------------------------------------------------------ status endpoint (what the member page calls)
    @patch("requests.get")
    def test_status_endpoint_asks_ioTec_and_settles_the_payment(self, get):
        pay = self.make_payment(age_minutes=2)
        get.return_value = self.status_of("Success", 1000)
        self.client.force_login(self.user)
        data = self.client.get(reverse("payments:status", args=[pay.pk])).json()["data"]
        self.assertEqual(data["status"], "success")
        self.assertFalse(data["provider_check_failed"])
        self.assertEqual(Subscription.objects.get(member=self.member).status, Subscription.Status.ACTIVE)

    def test_status_endpoint_flags_an_unreachable_provider(self):
        pay = self.make_payment(age_minutes=2)
        self.client.force_login(self.user)
        with patch.object(reconciliation, "fetch_collection_state", side_effect=IotecPayError("down")):
            data = self.client.get(reverse("payments:status", args=[pay.pk])).json()["data"]
        self.assertTrue(data["provider_check_failed"])
        self.assertEqual(data["status"], "sent_to_vendor")

    @patch("requests.get")
    def test_status_endpoint_rechecks_parked_payments_too(self, get):
        pay = self.make_payment(status=Payment.Status.REQUIRES_REVIEW, age_minutes=2 * 24 * 60)
        get.return_value = self.status_of("Success", 1000)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("payments:status", args=[pay.pk])).json()["data"]["status"], "success")

    def test_status_endpoint_is_owner_only(self):
        pay = self.make_payment()
        other = User.objects.create_user(phone="+256701400099", password="x", role=Role.MEMBER)
        self.client.force_login(other)
        self.assertEqual(self.client.get(reverse("payments:status", args=[pay.pk])).status_code, 404)

    # ------------------------------------------------------------------ what the member sees
    def banner(self):
        self.client.force_login(self.user)
        return self.client.get(reverse("member")).content.decode()

    def test_fresh_payment_tells_the_member_to_approve_on_their_phone(self):
        pay = self.make_payment(age_minutes=3)
        html = self.banner()
        self.assertIn("Payment pending — approve it on your phone.", html)
        self.assertIn(f'data-status-url="/api/v1/payments/{pay.pk}/"', html)
        self.assertIn("pending_payment.js", html)

    def test_old_payment_no_longer_claims_to_be_waiting_for_the_phone_prompt(self):
        self.make_payment(age_minutes=3 * 24 * 60)
        html = self.banner()
        self.assertIn("We haven't been able to confirm your last payment yet.", html)
        self.assertNotIn("approve it on your phone", html)
        self.assertIn("data-pending-check", html)                 # they can still press Check status

    def test_parked_payment_still_offers_check_status(self):
        self.make_payment(status=Payment.Status.REQUIRES_REVIEW, age_minutes=2 * 24 * 60)
        self.assertIn("data-pending-check", self.banner())

    def test_no_pending_payment_no_check_button(self):
        self.assertNotIn("data-pending-check", self.banner())
