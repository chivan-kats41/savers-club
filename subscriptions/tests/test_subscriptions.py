from django.test import TestCase
from django.urls import reverse

from accounts.models import Role, User
from core.models import Area
from members.models import Member
from subscriptions.models import Subscription, SubscriptionPayment, SubscriptionPlan
from subscriptions.services import SubscriptionError, confirm_payment, initiate_renewal, pause_subscription


class SubscriptionServiceTests(TestCase):
    def setUp(self):
        self.area = Area.objects.create(name="Testville")
        self.plan = SubscriptionPlan.objects.create(code="1k-monthly", label="Monthly", price=1000, period_days=30)
        user = User.objects.create_user(phone="+256700930000", password="pass12345", role=Role.MEMBER)
        self.member = Member.objects.create(user=user, area=self.area)

    def test_renewal_creates_pending_subscription_and_payment(self):
        payment = initiate_renewal(self.member)
        self.assertEqual(payment.status, SubscriptionPayment.Status.PENDING)
        subscription = Subscription.objects.get(member=self.member)
        self.assertEqual(subscription.status, Subscription.Status.PENDING)

    def test_second_renewal_blocked_while_payment_pending(self):
        initiate_renewal(self.member)
        with self.assertRaises(SubscriptionError):
            initiate_renewal(self.member)

    def test_confirm_payment_success_activates_subscription(self):
        payment = initiate_renewal(self.member)
        subscription = confirm_payment(payment, success=True, provider_transaction_id="TXN-1")
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, Subscription.Status.ACTIVE)
        self.assertIsNotNone(subscription.current_period_end)
        payment.refresh_from_db()
        self.assertEqual(payment.status, SubscriptionPayment.Status.SUCCESS)

    def test_confirm_payment_failure_does_not_activate(self):
        payment = initiate_renewal(self.member)
        subscription = confirm_payment(payment, success=False)
        self.assertEqual(subscription.status, Subscription.Status.PENDING)
        payment.refresh_from_db()
        self.assertEqual(payment.status, SubscriptionPayment.Status.FAILED)

    def test_double_confirm_rejected(self):
        payment = initiate_renewal(self.member)
        confirm_payment(payment, success=True)
        payment.refresh_from_db()
        with self.assertRaises(SubscriptionError):
            confirm_payment(payment, success=True)

    def test_pause_requires_active_subscription(self):
        with self.assertRaises(SubscriptionError):
            pause_subscription(self.member)

    def test_pause_active_subscription(self):
        payment = initiate_renewal(self.member)
        confirm_payment(payment, success=True)
        subscription = pause_subscription(self.member)
        self.assertEqual(subscription.status, Subscription.Status.PAUSED)


class SubscriptionAPITests(TestCase):
    def setUp(self):
        self.area = Area.objects.create(name="Testville")
        self.plan = SubscriptionPlan.objects.create(code="1k-monthly", label="Monthly", price=1000, period_days=30)
        self.member_user = User.objects.create_user(
            phone="+256700940000", password="pass12345", role=Role.MEMBER
        )
        self.member = Member.objects.create(user=self.member_user, area=self.area)
        self.merchant_user = User.objects.create_user(
            phone="+256700940001", password="pass12345", role=Role.MERCHANT
        )

    def test_anonymous_cannot_view_subscription(self):
        resp = self.client.get(reverse("subscriptions:my_subscription"))
        self.assertEqual(resp.status_code, 403)

    def test_non_member_role_forbidden(self):
        self.client.force_login(self.merchant_user)
        resp = self.client.get(reverse("subscriptions:my_subscription"))
        self.assertEqual(resp.status_code, 403)

    def test_member_can_renew_and_view(self):
        self.client.force_login(self.member_user)
        resp = self.client.post(reverse("subscriptions:renew"))
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(resp.json()["success"])
        resp = self.client.get(reverse("subscriptions:my_subscription"))
        self.assertEqual(resp.json()["data"]["status"], "pending")

    def test_double_renew_returns_400(self):
        self.client.force_login(self.member_user)
        self.client.post(reverse("subscriptions:renew"))
        resp = self.client.post(reverse("subscriptions:renew"))
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()["success"])

    def test_pause_without_active_subscription_returns_400(self):
        self.client.force_login(self.member_user)
        resp = self.client.post(reverse("subscriptions:pause"))
        self.assertEqual(resp.status_code, 400)
