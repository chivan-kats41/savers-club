"""Probes for specific claims from an external review that the earlier regression tests do not exercise:
DRF's own throttle behind a proxy, 2FA for staff with a non-admin role, the number-squatting window, and the legacy
renew endpoint leaving a payment with no provider behind it."""
from datetime import timedelta
from unittest.mock import Mock, patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework.throttling import SimpleRateThrottle

from decimal import Decimal

from accounts.models import Role, User
from core.tests.test_review_fixes import Base as _FixtureBase
from core.models import Area
from members.models import Member
from payments.models import Payment
from payments.services.payment_flow import PaymentError, initiate_subscription_payment
from subscriptions.models import Subscription, SubscriptionPayment, SubscriptionPlan

PASSWORD = "Pass12345!x"
IOTEC = dict(IOTEC_CLIENT_ID="id", IOTEC_CLIENT_SECRET="secret", IOTEC_WALLET_ID="wallet-123",
             IOTEC_BASE_URL="https://pay.iotec.io", IOTEC_TOKEN_URL="https://id.iotec.io/connect/token")
AUTH = Mock(status_code=200, json=lambda: {"access_token": "tok", "expires_in": 300})


class ProxyThrottleTests(TestCase):
    """DRF's throttles read X-Forwarded-For too (NUM_PROXIES). Behind one trusted proxy only the RIGHT-most entry, the
    one our own proxy wrote, may be believed, so a visitor cannot get fresh throttle buckets by forging the header."""

    def setUp(self):
        cache.clear()

    @override_settings(TRUSTED_PROXY_COUNT=1, REST_FRAMEWORK={"NUM_PROXIES": 1})
    def test_a_forged_leftmost_entry_cannot_dodge_a_drf_throttle(self):
        c = APIClient()
        statuses = []
        with patch.dict(SimpleRateThrottle.THROTTLE_RATES, {"geo_read": "3/hour"}):
            for i in range(5):
                r = c.get("/api/v1/geo/nearby-deals/", REMOTE_ADDR="172.18.0.2",
                          HTTP_X_FORWARDED_FOR=f"6.6.6.{i}, 203.0.113.9")     # nginx appended the real address on the right
                statuses.append(r.status_code)
        self.assertEqual(statuses, [200, 200, 200, 429, 429])

    @override_settings(TRUSTED_PROXY_COUNT=1, REST_FRAMEWORK={"NUM_PROXIES": 1})
    def test_different_real_visitors_still_get_their_own_buckets(self):
        c = APIClient()
        with patch.dict(SimpleRateThrottle.THROTTLE_RATES, {"geo_read": "2/hour"}):
            for ip in ("203.0.113.1", "203.0.113.2", "203.0.113.3"):
                for _ in range(2):
                    self.assertEqual(c.get("/api/v1/geo/nearby-deals/", REMOTE_ADDR="172.18.0.2",
                                           HTTP_X_FORWARDED_FOR=f"6.6.6.6, {ip}").status_code, 200)

    @override_settings(TRUSTED_PROXY_COUNT=0, REST_FRAMEWORK={"NUM_PROXIES": 0})
    def test_without_a_trusted_proxy_the_header_is_ignored_completely(self):
        c = APIClient()
        statuses = []
        with patch.dict(SimpleRateThrottle.THROTTLE_RATES, {"geo_read": "2/hour"}):
            for i in range(4):
                statuses.append(c.get("/api/v1/geo/nearby-deals/", REMOTE_ADDR="198.51.100.7",
                                      HTTP_X_FORWARDED_FOR=f"1.1.1.{i}").status_code)
        self.assertEqual(statuses, [200, 200, 429, 429])


@override_settings(ADMIN_REQUIRE_2FA=True)
class StaffTwoFactorTests(TestCase):
    """The 2FA gate on the admin areas is keyed on is_admin() OR is_staff, not on the role column alone."""

    def test_a_staff_user_with_a_non_admin_role_still_needs_2fa_on_django_admin(self):
        u = User.objects.create_user(phone="+256772600001", password=PASSWORD, role=Role.MEMBER, phone_verified=True)
        User.objects.filter(pk=u.pk).update(is_staff=True, is_superuser=True)
        self.client.force_login(User.objects.get(pk=u.pk))
        r = self.client.get("/django-admin/")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/accounts/2fa/", r["Location"])

    def test_the_admin_api_refuses_a_staff_user_without_2fa(self):
        u = User.objects.create_user(phone="+256772600002", password=PASSWORD, role=Role.MEMBER, phone_verified=True)
        User.objects.filter(pk=u.pk).update(is_staff=True)
        self.client.force_login(User.objects.get(pk=u.pk))
        self.assertEqual(self.client.get("/api/v1/admin/areas/").status_code, 403)

    def test_an_ordinary_member_is_not_caught_by_the_gate(self):
        User.objects.create_user(phone="+256772600003", password=PASSWORD, role=Role.MEMBER, phone_verified=True)
        self.client.login(username="+256772600003", password=PASSWORD)
        self.assertNotEqual(self.client.get("/").status_code, 403)


class SquattingWindowTests(TestCase):
    """What protects a phone number from being registered by someone who doesn't own it."""

    def setUp(self):
        cache.clear()
        self.area = Area.objects.create(name="Kireka")

    def register(self, phone):
        with patch("accounts.views._send_otp_dev"):
            return self.client.post(reverse("accounts:register"), {
                "phone": phone, "password": PASSWORD, "password_confirm": PASSWORD, "area": self.area.pk})

    def test_a_squatter_cannot_log_in_or_use_the_number_without_the_sms_code(self):
        self.register("+256772700001")
        victim_view = self.client.post(reverse("accounts:login"), {"identifier": "+256772700001", "password": PASSWORD})
        self.assertRedirects(victim_view, reverse("accounts:verify_phone"), fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_the_number_is_blocked_for_the_real_owner_for_at_most_a_day(self):
        self.register("+256772700002")
        self.client.logout()
        again = self.register("+256772700002")
        self.assertContains(again, "already exists")                              # the residual window
        User.objects.filter(phone="+256772700002").update(date_joined=timezone.now() - timedelta(hours=25))
        released = self.register("+256772700002")
        self.assertEqual(released.status_code, 302)                               # after 24 h the real owner can register
        self.assertEqual(User.objects.filter(phone="+256772700002").count(), 1)


@override_settings(**IOTEC)
class LegacyRenewEndpointTests(TestCase):
    """POST /api/v1/member/subscription/renew/ opens a pending SubscriptionPayment with NO provider payment behind it.
    The real payment flow must not be blocked by that leftover."""

    def setUp(self):
        cache.clear()
        area = Area.objects.create(name="Kireka")
        SubscriptionPlan.objects.create(code="1k-monthly", label="Monthly", price=1000, period_days=30)
        self.user = User.objects.create_user(phone="+256772800001", password=PASSWORD, role=Role.MEMBER, phone_verified=True)
        self.member = Member.objects.create(user=self.user, area=area)
        self.client = APIClient(); self.client.force_login(self.user)

    def pay(self):
        self.n = getattr(self, "n", 0) + 1
        with patch("requests.post") as post:
            post.side_effect = lambda url, *a, **k: AUTH if "connect/token" in url else Mock(
                status_code=200, json=lambda: {"id": f"t{self.n}", "status": "SentToVendor"})
            return initiate_subscription_payment(self.member, Payment.Method.MOBILE_MONEY, payer_phone="+256772800001")

    def test_a_leftover_from_the_legacy_endpoint_does_not_block_a_real_payment(self):
        r = self.client.post("/api/v1/member/subscription/renew/", {}, format="json")
        self.assertEqual(r.status_code, 201, r.content)                            # the orphan now exists...
        self.assertEqual(SubscriptionPayment.objects.filter(status="pending", provider_payment__isnull=True).count(), 1)
        payment = self.pay()                                                       # ...and must not stop a real payment
        self.assertIn(payment.status, (Payment.Status.PENDING, Payment.Status.SENT_TO_VENDOR))   # started, not failed
        self.assertEqual(SubscriptionPayment.objects.filter(status="pending").count(), 1)   # exactly one live attempt
        self.assertEqual(SubscriptionPayment.objects.filter(status="failed").count(), 1)    # the orphan was closed, not reused

    def test_two_real_payments_in_flight_are_still_refused(self):
        self.pay()
        with self.assertRaises(PaymentError):
            self.pay()                                                             # a genuine in-flight payment still blocks

    def test_a_payment_parked_for_review_does_not_block_a_new_purchase(self):
        first = self.pay()
        Payment.objects.filter(pk=first.pk).update(status=Payment.Status.REQUIRES_REVIEW)
        second = self.pay()
        self.assertIn(second.status, (Payment.Status.PENDING, Payment.Status.SENT_TO_VENDOR))
        self.assertEqual(Payment.objects.count(), 2)


class DeliveryCodeFallbackTests(_FixtureBase):
    """The delivery code is texted to the customer. If the SMS provider is down or unconfigured the customer must still be
    able to get it (in their account), or the delivery could never be confirmed."""

    def _arrived_job(self):
        from claims.services import claim_offer
        from deliveries.services import accept_job, mark_arrived, request_delivery

        claim = claim_offer(self.member, self.offer.id)
        job = request_delivery(claim, self.merchant, self.area, "x", "normal", Decimal("2000"))
        accept_job(self.rider, job.id)
        mark_arrived(self.rider, job.id)
        return job

    def test_working_sms_means_no_copy_of_the_code_is_stored(self):
        from deliveries.services import mark_picked_up
        from notifications.models import Notification

        job = self._arrived_job()
        with patch("notifications.services.sms_gateway.send_sms", return_value=True):
            _, raw = mark_picked_up(self.rider, job.id)
        self.assertFalse(Notification.objects.filter(user=self.memu, title="Your delivery code").exists())
        self.assertFalse(Notification.objects.filter(message__contains=raw).exists())

    def test_failed_sms_falls_back_to_an_in_app_only_message_the_customer_can_use(self):
        from deliveries.services import confirm_delivery, mark_on_route, mark_picked_up
        from notifications.models import Notification

        job = self._arrived_job()
        with patch("notifications.services.sms_gateway.send_sms", return_value=False):
            _, raw = mark_picked_up(self.rider, job.id)
        n = Notification.objects.get(user=self.memu, title="Your delivery code")
        self.assertIn(raw, n.message)
        self.assertEqual(n.metadata["_channels"], ["in_app"])          # never SMS'd again, never pushed to a lock screen
        mark_on_route(self.rider, job.id)
        self.assertEqual(confirm_delivery(self.rider, job.id, raw).status, "delivered")

    def test_the_fallback_message_is_not_sent_out_by_the_dispatcher(self):
        from deliveries.services import mark_picked_up
        from notifications import tasks
        from notifications.models import Notification

        job = self._arrived_job()
        with patch("notifications.services.sms_gateway.send_sms", return_value=False):
            mark_picked_up(self.rider, job.id)
        n = Notification.objects.get(title="Your delivery code")
        with patch.object(tasks.send_push_notification, "delay") as push, patch.object(tasks.send_sms_notification, "delay") as sms:
            tasks.dispatch_external_notification(n.id)
        push.assert_not_called(); sms.assert_not_called()
