"""Regression tests for the issues found in the code review (money flow, delivery OTP, auth, claims, plans)."""
from datetime import timedelta
from decimal import Decimal
from unittest.mock import Mock, patch

import requests
from django.core.cache import cache
from django.core.management import call_command
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import OTPRateLimited, PhoneVerification, Role, User
from claims.services import ClaimError, claim_offer, redeem_claim
from core.middleware import get_client_ip
from core.models import Area
from deliveries.models import DeliveryJob, DeliveryOTP, RiderEarning
from deliveries.services import DeliveryError, accept_job, confirm_delivery, mark_arrived, mark_on_route, mark_picked_up, request_delivery
from members.models import Member
from merchants.models import Merchant
from offers.models import Offer, OfferCategory
from payments.models import Payment, Withdrawal
from payments.services.iotec_client import IotecNotFound
from payments.services.payment_flow import PaymentError, initiate_subscription_payment, process_collection_callback
from payments.services.reconciliation import reconcile_payment, reconcile_withdrawal
from payments.services.withdrawal_flow import WithdrawalError, request_rider_withdrawal
from riders.models import Rider
from subscriptions.models import Subscription, SubscriptionPayment, SubscriptionPlan
from subscriptions.services import SubscriptionError, initiate_renewal

AUTH = Mock(status_code=200, json=lambda: {"access_token": "tok", "expires_in": 300})
IOTEC = dict(IOTEC_CLIENT_ID="a", IOTEC_CLIENT_SECRET="b", IOTEC_WALLET_ID="w",
             IOTEC_BASE_URL="https://pay.iotec.io", IOTEC_TOKEN_URL="https://id.iotec.io/connect/token")


def post_that(collect):
    """requests.post stand-in: token call succeeds, every other call does `collect()`."""
    def _post(url, *a, **k):
        if "connect/token" in url:
            return AUTH
        return collect()
    return _post


def timeout():
    raise requests.Timeout("read timed out")


def make_world():
    area = Area.objects.create(name="Testville")
    cat = OfferCategory.objects.create(key="soap", label="Soap")
    mu = User.objects.create_user(phone="+256700000001", password="Pass12345!x", role=Role.MERCHANT, phone_verified=True)
    merchant = Merchant.objects.create(user=mu, business_name="Shop", category=cat, area=area)
    memu = User.objects.create_user(phone="+256700000002", password="Pass12345!x", role=Role.MEMBER, phone_verified=True)
    member = Member.objects.create(user=memu, area=area)
    ru = User.objects.create_user(phone="+256700000003", password="Pass12345!x", role=Role.RIDER, phone_verified=True)
    rider = Rider.objects.create(user=ru, area=area, status=Rider.Status.VERIFIED)
    offer = Offer.objects.create(
        merchant=merchant, category=cat, area=area, item_name="Soap", normal_price=3000, member_price=2500,
        quantity=5, expires_at=timezone.now() + timedelta(days=1), status=Offer.Status.ACTIVE, delivery_available=True,
    )
    return area, merchant, member, memu, rider, ru, offer


class Base(TestCase):
    def setUp(self):
        cache.clear()
        self.area, self.merchant, self.member, self.memu, self.rider, self.ru, self.offer = make_world()


# ------------------------------------------------------------------ delivery ------------------------------------------
class DeliveryCodeTests(Base):
    def _on_route_job(self):
        claim = claim_offer(self.member, self.offer.id)
        job = request_delivery(claim, self.merchant, self.area, "x", "normal", Decimal("2000"))
        accept_job(self.rider, job.id)
        mark_arrived(self.rider, job.id)
        return job

    def test_code_is_texted_to_the_customer_not_just_returned_to_the_rider(self):
        job = self._on_route_job()
        with patch("notifications.services.sms_gateway.send_sms", return_value=True) as sms:
            _, raw = mark_picked_up(self.rider, job.id)
        sms.assert_called_once()
        phone, body = sms.call_args.args[:2]
        self.assertEqual(phone, self.memu.phone)
        self.assertIn(raw, body)

    def test_wrong_codes_are_counted_and_lock_the_code(self):
        job = self._on_route_job()
        with patch("notifications.services.sms_gateway.send_sms", return_value=True):
            _, raw = mark_picked_up(self.rider, job.id)
        mark_on_route(self.rider, job.id)
        wrong = "000000" if raw != "000000" else "111111"
        for _ in range(7):
            with self.assertRaises(DeliveryError):
                confirm_delivery(self.rider, job.id, wrong)
        otp = DeliveryOTP.objects.get(job=job)
        self.assertEqual(otp.attempts, otp.max_attempts)
        with self.assertRaises(DeliveryError):          # even the right code is refused once locked
            confirm_delivery(self.rider, job.id, raw)
        self.assertFalse(RiderEarning.objects.filter(delivery_job=job).exists())

    def test_right_code_still_delivers(self):
        job = self._on_route_job()
        with patch("notifications.services.sms_gateway.send_sms", return_value=True):
            _, raw = mark_picked_up(self.rider, job.id)
        mark_on_route(self.rider, job.id)
        confirm_delivery(self.rider, job.id, raw)
        self.assertTrue(RiderEarning.objects.filter(delivery_job=job).exists())


# ------------------------------------------------------------------ withdrawals ---------------------------------------
@override_settings(**IOTEC)
class WithdrawalSafetyTests(Base):
    def setUp(self):
        super().setUp()
        job = DeliveryJob.objects.create(pickup_merchant=self.merchant, dropoff_area=self.area, dropoff_address="x",
                                         fare=Decimal("10000"), status=DeliveryJob.Status.DELIVERED)
        RiderEarning.objects.create(rider=self.rider, delivery_job=job, gross_amount=10000, commission_amount=0, net_amount=10000)

    def test_timeout_keeps_a_pending_record_and_reserves_the_balance(self):
        with patch("requests.post", side_effect=post_that(timeout)):
            w = request_rider_withdrawal(self.rider, Decimal("6000"), "0772123456")
        self.assertEqual(w.status, Withdrawal.Status.PENDING)
        self.assertEqual(Withdrawal.objects.count(), 1)
        # the money may already be gone, so the same balance cannot be withdrawn again
        with patch("requests.post", side_effect=post_that(timeout)):
            with self.assertRaises(WithdrawalError):
                request_rider_withdrawal(self.rider, Decimal("6000"), "0772123456")

    def test_definite_rejection_is_recorded_failed_and_releases_the_balance(self):
        rejected = lambda: Mock(status_code=400, json=lambda: {"message": "Invalid wallet"})
        with patch("requests.post", side_effect=post_that(rejected)):
            with self.assertRaises(WithdrawalError):
                request_rider_withdrawal(self.rider, Decimal("6000"), "0772123456")
        self.assertEqual(Withdrawal.objects.get().status, Withdrawal.Status.FAILED)
        with patch("requests.post", side_effect=post_that(lambda: Mock(status_code=200, json=lambda: {"id": "t1", "status": "Pending"}))):
            request_rider_withdrawal(self.rider, Decimal("6000"), "0772123456")   # balance is free again

    def test_nan_and_garbage_amounts_are_rejected_not_500(self):
        c = APIClient(raise_request_exception=False)
        c.force_login(self.ru)
        for bad in ("NaN", "Infinity", "-5", "abc"):
            r = c.post("/api/v1/rider/withdraw/", {"amount": bad, "phone": "0772123456"}, format="json")
            self.assertEqual(r.status_code, 400, bad)

    def test_reconciliation_closes_a_withdrawal_ioTec_never_received(self):
        with patch("requests.post", side_effect=post_that(timeout)):
            w = request_rider_withdrawal(self.rider, Decimal("6000"), "0772123456")
        Withdrawal.objects.filter(pk=w.pk).update(created_at=timezone.now() - timedelta(minutes=30))
        w.refresh_from_db()
        with patch("payments.services.reconciliation.get_disbursement_by_external_id", side_effect=IotecNotFound("nope")):
            reconcile_withdrawal(w)
        w.refresh_from_db()
        self.assertEqual(w.status, Withdrawal.Status.FAILED)


# ------------------------------------------------------------------ plans & subscription payments ---------------------
@override_settings(**IOTEC)
class PlanSelectionTests(Base):
    def setUp(self):
        super().setUp()
        call_command("seed_subscription_plans", verbosity=0)
        self.monthly = SubscriptionPlan.objects.get(code="1k-monthly")
        self.quarterly = SubscriptionPlan.objects.get(code="3k-quarterly")
        self.yearly = SubscriptionPlan.objects.get(code="10k-year")
        self.ok = lambda: Mock(status_code=200, json=lambda: {"id": "txn", "status": "Pending"})

    def _pay(self, code):
        with patch("requests.post", side_effect=post_that(self.ok)):
            p = initiate_subscription_payment(self.member, Payment.Method.MOBILE_MONEY, payer_phone="0772123456", plan_code=code)
        process_collection_callback({"externalId": str(p.internal_reference), "status": "Success", "transactionId": "txn"})
        return p

    def test_only_monthly_quarterly_and_yearly_are_offered_by_default(self):
        self.assertEqual(
            set(SubscriptionPlan.objects.filter(is_active=True).values_list("code", flat=True)),
            {"1k-monthly", "3k-quarterly", "10k-year"},
        )

    def test_each_plan_charges_its_price_and_grants_its_period(self):
        for i, plan in enumerate((self.monthly, self.quarterly, self.yearly)):
            user = User.objects.create_user(phone=f"+2567011000{i}", password="Pass12345!x", role=Role.MEMBER, phone_verified=True)
            member = Member.objects.create(user=user, area=self.area)
            with patch("requests.post", side_effect=post_that(self.ok)):
                p = initiate_subscription_payment(member, Payment.Method.MOBILE_MONEY, payer_phone="0772123456", plan_code=plan.code)
            process_collection_callback({"externalId": str(p.internal_reference), "status": "Success", "transactionId": f"t{i}"})
            self.assertEqual(p.amount, plan.price)
            sub = Subscription.objects.get(member=member)
            self.assertEqual(sub.plan, plan)
            self.assertEqual(sub.status, Subscription.Status.ACTIVE)
            self.assertAlmostEqual((sub.current_period_end - sub.current_period_start).days, plan.period_days, delta=1)

    def test_switching_plan_keeps_one_subscription_and_stacks_the_time(self):
        self._pay("1k-monthly")
        first_end = Subscription.objects.get().current_period_end
        self._pay("10k-year")
        self.assertEqual(Subscription.objects.filter(member=self.member).count(), 1)
        sub = Subscription.objects.get()
        self.assertEqual(sub.plan, self.yearly)
        self.assertAlmostEqual((sub.current_period_end - first_end).days, 365, delta=1)

    def test_unknown_or_inactive_plan_is_refused(self):
        with self.assertRaises(PaymentError):
            initiate_subscription_payment(self.member, Payment.Method.MOBILE_MONEY, payer_phone="0772123456", plan_code="nope")
        SubscriptionPlan.objects.filter(code="6k-semi").update(is_active=False)
        with self.assertRaises(PaymentError):
            initiate_subscription_payment(self.member, Payment.Method.MOBILE_MONEY, payer_phone="0772123456", plan_code="6k-semi")

    def test_api_accepts_a_plan_choice(self):
        c = APIClient(raise_request_exception=False)
        c.force_login(self.memu)
        with patch("requests.post", side_effect=post_that(self.ok)):
            r = c.post("/api/v1/payments/initiate/", {"purpose": "subscription", "plan": "3k-quarterly",
                                                       "method": "mobile_money", "phone": "0772123456"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(Payment.objects.get().amount, Decimal("3000"))

    def test_member_page_lists_the_plans(self):
        c = Client()
        c.force_login(self.memu)
        html = c.get(reverse("member")).content.decode()
        for label in ("Monthly", "Quarterly", "Yearly Promo"):
            self.assertIn(label, html)
        self.assertIn('name="plan"', html)

    # --- money-safety of the initiation itself
    def test_timeout_leaves_payment_pending_for_reconciliation_instead_of_vanishing(self):
        with patch("requests.post", side_effect=post_that(timeout)):
            p = initiate_subscription_payment(self.member, Payment.Method.MOBILE_MONEY, payer_phone="0772123456", plan_code="1k-monthly")
        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(p.status, Payment.Status.PENDING)
        self.assertEqual(SubscriptionPayment.objects.get().status, SubscriptionPayment.Status.PENDING)
        # a late callback from ioTec still finds the record and activates the plan
        process_collection_callback({"externalId": str(p.internal_reference), "status": "Success", "transactionId": "late"})
        self.assertEqual(Subscription.objects.get().status, Subscription.Status.ACTIVE)

    def test_definite_rejection_fails_the_payment_and_lets_the_member_retry(self):
        rejected = lambda: Mock(status_code=400, json=lambda: {"message": "Bad number"})
        with patch("requests.post", side_effect=post_that(rejected)):
            with self.assertRaises(PaymentError):
                initiate_subscription_payment(self.member, Payment.Method.MOBILE_MONEY, payer_phone="0772123456", plan_code="1k-monthly")
        self.assertEqual(Payment.objects.get().status, Payment.Status.FAILED)
        self.assertEqual(SubscriptionPayment.objects.get().status, SubscriptionPayment.Status.FAILED)
        self._pay("1k-monthly")   # not locked out

    def test_reconciliation_closes_a_payment_ioTec_never_received(self):
        with patch("requests.post", side_effect=post_that(timeout)):
            p = initiate_subscription_payment(self.member, Payment.Method.MOBILE_MONEY, payer_phone="0772123456", plan_code="1k-monthly")
        Payment.objects.filter(pk=p.pk).update(created_at=timezone.now() - timedelta(minutes=30))
        p.refresh_from_db()
        with patch("payments.services.reconciliation.get_collection_by_external_id", side_effect=IotecNotFound("nope")):
            reconcile_payment(p)
        p.refresh_from_db()
        self.assertEqual(p.status, Payment.Status.FAILED)
        self.assertEqual(SubscriptionPayment.objects.get().status, SubscriptionPayment.Status.FAILED)

    # --- stale pending payments no longer lock a member out
    def test_abandoned_orphan_pending_payment_stops_blocking_after_grace(self):
        initiate_renewal(self.member)                       # e.g. the legacy renew endpoint: no provider payment behind it
        with self.assertRaises(SubscriptionError):
            initiate_renewal(self.member)                   # still blocked inside the grace window
        SubscriptionPayment.objects.update(created_at=timezone.now() - timedelta(minutes=20))
        initiate_renewal(self.member)                       # now allowed

    def test_payment_parked_for_review_does_not_block_a_new_purchase(self):
        with patch("requests.post", side_effect=post_that(self.ok)):
            p = initiate_subscription_payment(self.member, Payment.Method.MOBILE_MONEY, payer_phone="0772123456", plan_code="1k-monthly")
        Payment.objects.filter(pk=p.pk).update(status=Payment.Status.REQUIRES_REVIEW)
        self._pay("1k-monthly")


# ------------------------------------------------------------------ client IP / rate limits ---------------------------
class ClientIpTests(TestCase):
    def _ip(self, xff, trusted):
        req = RequestFactory().get("/", HTTP_X_FORWARDED_FOR=xff, REMOTE_ADDR="10.0.0.1")
        with override_settings(TRUSTED_PROXY_COUNT=trusted):
            return get_client_ip(req)

    def test_forged_header_is_ignored_without_a_trusted_proxy(self):
        self.assertEqual(self._ip("6.6.6.6", 0), "10.0.0.1")

    def test_leftmost_forged_entry_is_not_trusted_behind_one_proxy(self):
        self.assertEqual(self._ip("6.6.6.6, 203.0.113.9", 1), "203.0.113.9")

    def test_rotating_header_cannot_dodge_the_register_limit(self):
        cache.clear()
        with override_settings(TRUSTED_PROXY_COUNT=0):
            codes = [Client().post(reverse("accounts:register"), {}, HTTP_X_FORWARDED_FOR=f"9.9.9.{i}").status_code for i in range(12)]
        self.assertIn(429, codes)


# ------------------------------------------------------------------ OTP + verification --------------------------------
class OtpAndVerificationTests(Base):
    def test_codes_are_six_digits(self):
        _, raw = PhoneVerification.issue(self.memu, PhoneVerification.Purpose.PASSWORD_RESET)
        self.assertRegex(raw, r"^\d{6}$")

    def test_issuing_is_capped_per_account(self):
        for _ in range(PhoneVerification.MAX_ISSUED_PER_HOUR):
            PhoneVerification.issue(self.memu, PhoneVerification.Purpose.PASSWORD_RESET)
        with self.assertRaises(OTPRateLimited):
            PhoneVerification.issue(self.memu, PhoneVerification.Purpose.PASSWORD_RESET)

    def test_unverified_user_cannot_log_in_until_verified(self):
        User.objects.create_user(phone="+256700000099", password="Pass12345!x", role=Role.MEMBER)
        r = Client().post(reverse("accounts:login"), {"identifier": "+256700000099", "password": "Pass12345!x"})
        self.assertRedirects(r, reverse("accounts:verify_phone"))

    def test_number_held_by_a_never_verified_account_is_released_after_a_day(self):
        old = User.objects.create_user(phone="+256700000077", password="Pass12345!x", role=Role.MEMBER)
        User.objects.filter(pk=old.pk).update(date_joined=timezone.now() - timedelta(days=2))
        r = Client().post(reverse("accounts:register"), {
            "phone": "+256700000077", "email": "new@example.com", "first_name": "N", "last_name": "U", "area": self.area.pk,
            "password": "Str0ng!Passw0rd", "password_confirm": "Str0ng!Passw0rd"})
        self.assertRedirects(r, reverse("accounts:verify_phone"))
        self.assertNotEqual(User.objects.get(phone="+256700000077").pk, old.pk)

    def test_number_of_a_recent_unverified_account_is_not_released(self):
        User.objects.create_user(phone="+256700000078", password="Pass12345!x", role=Role.MEMBER)
        r = Client().post(reverse("accounts:register"), {
            "phone": "+256700000078", "email": "n2@example.com", "first_name": "N", "last_name": "U", "area": self.area.pk,
            "password": "Str0ng!Passw0rd", "password_confirm": "Str0ng!Passw0rd"})
        self.assertEqual(r.status_code, 200)

    def test_failed_member_creation_leaves_no_orphan_user(self):
        with patch("members.models.Member.objects.create", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                Client().post(reverse("accounts:register"), {
                    "phone": "+256700000555", "email": "o@example.com", "first_name": "N", "last_name": "U",
                    "area": self.area.pk, "password": "Str0ng!Passw0rd", "password_confirm": "Str0ng!Passw0rd"})
        self.assertFalse(User.objects.filter(phone="+256700000555").exists())


# ------------------------------------------------------------------ claims ---------------------------------------------
class ClaimTests(Base):
    @override_settings(REQUIRE_SUBSCRIPTION_TO_CLAIM=True)
    def test_claiming_needs_an_active_subscription(self):
        with self.assertRaises(ClaimError):
            claim_offer(self.member, self.offer.id)
        plan = SubscriptionPlan.objects.create(code="m", label="Monthly", price=1000, period_days=30)
        Subscription.objects.create(member=self.member, plan=plan, status=Subscription.Status.ACTIVE,
                                    current_period_start=timezone.now(), current_period_end=timezone.now() + timedelta(days=5))
        self.assertEqual(claim_offer(self.member, self.offer.id).status, "claimed")

    @override_settings(REQUIRE_SUBSCRIPTION_TO_CLAIM=True)
    def test_expired_subscription_cannot_claim(self):
        plan = SubscriptionPlan.objects.create(code="m", label="Monthly", price=1000, period_days=30)
        Subscription.objects.create(member=self.member, plan=plan, status=Subscription.Status.ACTIVE,
                                    current_period_start=timezone.now() - timedelta(days=40), current_period_end=timezone.now() - timedelta(days=10))
        with self.assertRaises(ClaimError):
            claim_offer(self.member, self.offer.id)

    def test_unknown_offer_is_a_400_not_a_500(self):
        c = APIClient(raise_request_exception=False)
        c.force_login(self.memu)
        self.assertEqual(c.post("/api/v1/member/offers/99999/claim/").status_code, 400)

    def test_claim_code_collision_is_retried(self):
        first = claim_offer(self.member, self.offer.id)
        other = User.objects.create_user(phone="+256700000010", password="Pass12345!x", role=Role.MEMBER, phone_verified=True)
        member2 = Member.objects.create(user=other, area=self.area)
        codes = iter([first.code, first.code, "1K-ZZZZZZ"])
        with patch("claims.models.generate_claim_code", side_effect=lambda: next(codes)):
            # the model default was bound at import, so patch the field default too
            from claims.models import OfferClaim
            field = OfferClaim._meta.get_field("code")
            original = field.default
            field.default = lambda: next(codes)
            try:
                second = claim_offer(member2, self.offer.id)
            finally:
                field.default = original
        self.assertNotEqual(second.code, first.code)

    def test_claim_code_is_long_enough_to_avoid_routine_collisions(self):
        self.assertEqual(len(claim_offer(self.member, self.offer.id).code), len("1K-") + 6)

    def test_expired_claim_is_restocked_when_the_merchant_tries_to_redeem_it(self):
        claim = claim_offer(self.member, self.offer.id)
        self.offer.refresh_from_db()
        stock_after_claim = self.offer.quantity
        type(claim).objects.filter(pk=claim.pk).update(expires_at=timezone.now() - timedelta(hours=1))
        with self.assertRaises(ClaimError):
            redeem_claim(self.merchant, claim.code)
        self.offer.refresh_from_db()
        self.assertEqual(self.offer.quantity, stock_after_claim + 1)


class ApiDocsTests(TestCase):
    def test_docs_are_not_exposed_unless_enabled(self):
        self.assertEqual(Client().get("/api/docs/").status_code, 404)


# ================================================================== delivery fare: online or cash on delivery ======
from accounts.models import User as _U  # noqa: E402
from deliveries.models import DeliveryJob as _J  # noqa: E402
from deliveries.services import cancel_delivery, expire_unpaid_deliveries, mark_failed, open_jobs_for_riders  # noqa: E402
from payments.services.payment_flow import initiate_delivery_payment  # noqa: E402
from payments.services.withdrawal_flow import available_rider_balance  # noqa: E402


def _deliver(test, job, rider):
    accept_job(rider, job.id); mark_arrived(rider, job.id)
    with patch("notifications.services.sms_gateway.send_sms", return_value=True):
        _, raw = mark_picked_up(rider, job.id)
    mark_on_route(rider, job.id)
    return confirm_delivery(rider, job.id, raw)


@override_settings(**IOTEC)
class DeliveryPaymentTests(Base):
    def setUp(self):
        super().setUp()
        self.ok = lambda: Mock(status_code=200, json=lambda: {"id": "txn", "status": "Pending"})

    def _request(self, method, delivery_type="normal", fare="2000"):
        claim = claim_offer(self.member, self.offer.id)
        return request_delivery(claim, self.merchant, self.area, "x", delivery_type, Decimal(fare), payment_method=method)

    # ----- cash on delivery
    def test_cash_job_is_visible_to_riders_immediately(self):
        job = self._request("cash")
        self.assertEqual(job.payment_status, _J.PaymentStatus.CASH_PENDING)
        self.assertIn(job, open_jobs_for_riders())

    def test_cash_delivery_does_not_pay_the_rider_the_fare_a_second_time(self):
        job = self._request("cash")
        _deliver(self, job, self.rider)
        job.refresh_from_db()
        self.assertEqual(job.payment_status, _J.PaymentStatus.CASH_COLLECTED)
        earning = RiderEarning.objects.get(delivery_job=job)
        self.assertEqual(earning.cash_collected, Decimal("2000"))
        self.assertEqual(available_rider_balance(self.rider), Decimal("0"))      # earned 2000, already holds 2000 cash

    def test_cash_shared_route_leaves_the_rider_owing_the_commission(self):
        job = self._request("cash", delivery_type="shared_route", fare="2000")
        _deliver(self, job, self.rider)
        earning = RiderEarning.objects.get(delivery_job=job)
        self.assertGreater(earning.commission_amount, 0)
        self.assertEqual(available_rider_balance(self.rider), -earning.commission_amount)
        with patch("requests.post", side_effect=post_that(lambda: Mock(status_code=200, json=lambda: {"id": "t", "status": "Pending"}))):
            with self.assertRaises(WithdrawalError):                              # cannot cash out while owing
                request_rider_withdrawal(self.rider, Decimal("1000"), "0772123456")

    def test_online_delivery_credits_the_rider_in_full(self):
        job = self._request("online")
        _J.objects.filter(pk=job.pk).update(payment_status=_J.PaymentStatus.PAID)
        job.refresh_from_db()
        _deliver(self, job, self.rider)
        self.assertEqual(available_rider_balance(self.rider), Decimal("2000"))

    # ----- online payment
    def test_unpaid_online_job_is_hidden_and_cannot_be_accepted(self):
        job = self._request("online")
        self.assertEqual(job.payment_status, _J.PaymentStatus.UNPAID)
        self.assertNotIn(job, open_jobs_for_riders())
        with self.assertRaises(DeliveryError):
            accept_job(self.rider, job.id)

    def test_successful_payment_releases_the_job_to_riders(self):
        job = self._request("online")
        with patch("requests.post", side_effect=post_that(self.ok)):
            p = initiate_delivery_payment(self.member, job, Payment.Method.MOBILE_MONEY, payer_phone="0772123456")
        self.assertEqual(p.amount, job.fare)
        self.assertEqual(p.purpose, Payment.Purpose.DELIVERY)
        process_collection_callback({"externalId": str(p.internal_reference), "status": "Success", "transactionId": "t1"})
        job.refresh_from_db()
        self.assertEqual(job.payment_status, _J.PaymentStatus.PAID)
        self.assertIn(job, open_jobs_for_riders())
        process_collection_callback({"externalId": str(p.internal_reference), "status": "Success", "transactionId": "t1"})  # repeat is harmless
        accept_job(self.rider, job.id)

    def test_failed_payment_keeps_it_unpaid_and_retry_is_allowed(self):
        job = self._request("online")
        with patch("requests.post", side_effect=post_that(self.ok)):
            p = initiate_delivery_payment(self.member, job, Payment.Method.MOBILE_MONEY, payer_phone="0772123456")
            with self.assertRaises(PaymentError):                                 # one attempt in flight at a time
                initiate_delivery_payment(self.member, job, Payment.Method.MOBILE_MONEY, payer_phone="0772123456")
        process_collection_callback({"externalId": str(p.internal_reference), "status": "Failed"})
        job.refresh_from_db()
        self.assertEqual(job.payment_status, _J.PaymentStatus.UNPAID)
        with patch("requests.post", side_effect=post_that(self.ok)):
            initiate_delivery_payment(self.member, job, Payment.Method.MOBILE_MONEY, payer_phone="0772123456")

    def test_only_the_owner_can_pay_and_cash_jobs_cannot_be_paid_online(self):
        job = self._request("online")
        other = User.objects.create_user(phone="+256700000044", password="Pass12345!x", role=Role.MEMBER, phone_verified=True)
        stranger = Member.objects.create(user=other, area=self.area)
        with self.assertRaises(PaymentError):
            initiate_delivery_payment(stranger, job, Payment.Method.MOBILE_MONEY, payer_phone="0772123456")
        cash = _J.objects.create(pickup_merchant=self.merchant, dropoff_area=self.area, dropoff_address="y", fare=2000,
                                 payment_method="cash", payment_status="cash_pending")
        with self.assertRaises(PaymentError):
            initiate_delivery_payment(self.member, cash, Payment.Method.MOBILE_MONEY, payer_phone="0772123456")

    def test_abandoned_unpaid_job_is_cancelled_and_frees_the_claim(self):
        job = self._request("online")
        _J.objects.filter(pk=job.pk).update(created_at=timezone.now() - timedelta(minutes=45))
        self.assertEqual(expire_unpaid_deliveries(), 1)
        job.refresh_from_db()
        self.assertEqual(job.status, _J.Status.CANCELLED)
        self.assertIsNone(job.claim_id)

    def test_job_with_a_payment_in_flight_is_not_cancelled(self):
        job = self._request("online")
        with patch("requests.post", side_effect=post_that(self.ok)):
            initiate_delivery_payment(self.member, job, Payment.Method.MOBILE_MONEY, payer_phone="0772123456")
        _J.objects.filter(pk=job.pk).update(created_at=timezone.now() - timedelta(minutes=45))
        self.assertEqual(expire_unpaid_deliveries(), 0)

    def test_paid_job_that_fails_or_is_cancelled_is_flagged_for_refund(self):
        job = self._request("online")
        _J.objects.filter(pk=job.pk).update(payment_status=_J.PaymentStatus.PAID)
        job.refresh_from_db()
        cancelled = cancel_delivery(job)
        self.assertEqual(cancelled.payment_status, _J.PaymentStatus.REFUND_DUE)

        offer2 = Offer.objects.create(
            merchant=self.merchant, category=self.offer.category, area=self.area, item_name="Soap 2", normal_price=3000,
            member_price=2500, quantity=5, expires_at=timezone.now() + timedelta(days=1),
            status=Offer.Status.ACTIVE, delivery_available=True)
        job2 = request_delivery(claim_offer(self.member, offer2.id), self.merchant, self.area, "x", "normal", Decimal("2000"),
                                payment_method="online")
        _J.objects.filter(pk=job2.pk).update(payment_status=_J.PaymentStatus.PAID)
        accept_job(self.rider, job2.id)
        mark_failed(self.rider, job2.id, "customer unreachable")
        job2.refresh_from_db()
        self.assertEqual(job2.payment_status, _J.PaymentStatus.REFUND_DUE)

    def test_payment_arriving_after_cancellation_is_flagged_not_activated(self):
        job = self._request("online")
        with patch("requests.post", side_effect=post_that(self.ok)):
            p = initiate_delivery_payment(self.member, job, Payment.Method.MOBILE_MONEY, payer_phone="0772123456")
        cancel_delivery(job)
        process_collection_callback({"externalId": str(p.internal_reference), "status": "Success", "transactionId": "late"})
        job.refresh_from_db()
        self.assertEqual(job.payment_status, _J.PaymentStatus.REFUND_DUE)

    # ----- API
    def _api(self):
        c = APIClient(raise_request_exception=False)
        c.force_login(self.memu)
        return c

    def test_api_cash_request(self):
        r = self._api().post("/api/v1/member/delivery/request/", {
            "claim_code": claim_offer(self.member, self.offer.id).code, "dropoff_area": self.area.name,
            "dropoff_address": "Near the market", "delivery_type": "normal", "payment_method": "cash"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["data"]["payment_status"], "cash_pending")

    def test_api_online_request_starts_a_payment(self):
        with patch("requests.post", side_effect=post_that(self.ok)):
            r = self._api().post("/api/v1/member/delivery/request/", {
                "claim_code": claim_offer(self.member, self.offer.id).code, "dropoff_area": self.area.name,
                "dropoff_address": "Near the market", "delivery_type": "normal", "payment_method": "online",
                "method": "mobile_money", "phone": "0772123456"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["data"]["payment_status"], "unpaid")
        self.assertEqual(Payment.objects.get().purpose, "delivery")

    def test_api_online_request_that_cannot_start_payment_leaves_no_stuck_job(self):
        r = self._api().post("/api/v1/member/delivery/request/", {
            "claim_code": claim_offer(self.member, self.offer.id).code, "dropoff_area": self.area.name,
            "dropoff_address": "Near the market", "delivery_type": "normal", "payment_method": "online",
            "method": "mobile_money", "phone": ""}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(_J.objects.filter(status=_J.Status.REQUESTED).count(), 0)

    def test_api_rejects_unknown_payment_method(self):
        r = self._api().post("/api/v1/member/delivery/request/", {
            "claim_code": claim_offer(self.member, self.offer.id).code, "dropoff_area": self.area.name,
            "dropoff_address": "x", "delivery_type": "normal", "payment_method": "barter"}, format="json")
        self.assertEqual(r.status_code, 400)


# ================================================================== referral rewards are payable =====================
from members.models import ReferralReward  # noqa: E402
from members.services import credit_referral_rewards  # noqa: E402
from payments.services.withdrawal_flow import available_referral_balance, request_referral_withdrawal  # noqa: E402


@override_settings(**IOTEC)
class ReferralPayoutTests(Base):
    def setUp(self):
        super().setUp()
        ru = User.objects.create_user(phone="+256700000060", password="Pass12345!x", role=Role.MEMBER, phone_verified=True)
        self.friend = Member.objects.create(user=ru, area=self.area, referred_by=self.member)
        self.reward = ReferralReward.objects.create(referrer=self.member, referred_member=self.friend, amount=Decimal("2500"))
        self.ok = lambda: Mock(status_code=200, json=lambda: {"id": "t", "status": "Pending"})

    def test_reward_is_held_then_credited(self):
        self.assertEqual(credit_referral_rewards(), 0)                  # too new
        self.assertEqual(available_referral_balance(self.member), 0)
        ReferralReward.objects.filter(pk=self.reward.pk).update(created_at=timezone.now() - timedelta(days=8))
        self.assertEqual(credit_referral_rewards(), 1)
        self.reward.refresh_from_db()
        self.assertEqual(self.reward.status, "credited")
        self.assertEqual(available_referral_balance(self.member), Decimal("2500"))
        self.assertEqual(credit_referral_rewards(), 0)                  # idempotent

    def test_credited_reward_can_be_withdrawn_once(self):
        ReferralReward.objects.filter(pk=self.reward.pk).update(status="credited", created_at=timezone.now() - timedelta(days=8))
        with patch("requests.post", side_effect=post_that(self.ok)):
            w = request_referral_withdrawal(self.member, Decimal("2500"), "0772123456")
            self.assertEqual(w.source, Withdrawal.Source.REFERRAL_REWARDS)
            with self.assertRaises(WithdrawalError):
                request_referral_withdrawal(self.member, Decimal("2500"), "0772123456")
        self.assertEqual(available_referral_balance(self.member), 0)

    def test_pending_reward_cannot_be_withdrawn(self):
        with self.assertRaises(WithdrawalError):
            request_referral_withdrawal(self.member, Decimal("2500"), "0772123456")

    def test_referral_and_rider_balances_do_not_mix(self):
        ReferralReward.objects.filter(pk=self.reward.pk).update(status="credited")
        Withdrawal.objects.create(user=self.memu, source=Withdrawal.Source.RIDER_EARNINGS, amount=100, fee=0, net_amount=100, phone="0772123456")
        self.assertEqual(available_referral_balance(self.member), Decimal("2500"))

    def test_api_withdraw(self):
        ReferralReward.objects.filter(pk=self.reward.pk).update(status="credited")
        c = APIClient(raise_request_exception=False)
        c.force_login(self.memu)
        from accounts.models import PhoneVerification

        _, code = PhoneVerification.issue(self.memu, PhoneVerification.Purpose.WITHDRAWAL)   # what "Send code" does
        with patch("requests.post", side_effect=post_that(self.ok)):
            r = c.post("/api/v1/member/referrals/withdraw/", {"amount": "2500", "phone": "0772123456", "code": code}, format="json")
            self.assertEqual(r.status_code, 201, r.content)
            self.assertEqual(c.post("/api/v1/member/referrals/withdraw/", {"amount": "NaN", "phone": "0772123456"}, format="json").status_code, 400)


# ================================================================== two-factor secrets ===============================
from accounts import totp as _totp  # noqa: E402


class TotpHardeningTests(Base):
    def test_secret_is_encrypted_at_rest_and_round_trips(self):
        raw = _totp.new_secret()
        self.memu.set_totp_secret(raw)
        self.memu.save()
        stored = User.objects.get(pk=self.memu.pk).totp_secret
        self.assertTrue(stored.startswith("enc1:"))
        self.assertNotIn(raw, stored)
        self.assertEqual(User.objects.get(pk=self.memu.pk).get_totp_secret(), raw)

    def test_legacy_plaintext_secret_still_works(self):
        raw = _totp.new_secret()
        User.objects.filter(pk=self.memu.pk).update(totp_secret=raw)
        self.assertEqual(User.objects.get(pk=self.memu.pk).get_totp_secret(), raw)

    def test_a_code_can_only_be_used_once(self):
        raw = _totp.new_secret()
        self.memu.set_totp_secret(raw)
        self.memu.save()
        code = _totp._code(raw, int(timezone.now().timestamp() // 30))
        self.assertTrue(self.memu.consume_totp_code(code))
        fresh = User.objects.get(pk=self.memu.pk)
        self.assertFalse(fresh.consume_totp_code(code))             # replay refused
        self.assertFalse(self.memu.consume_totp_code(code))


class RunPeriodicTests(TestCase):
    def test_once_runs_every_job_without_error(self):
        from io import StringIO
        call_command("run_periodic", "--once", stdout=StringIO())
