from datetime import timedelta

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Role, User
from core.models import Area, RiskEvent
from members.models import Member


class RateLimitTests(TestCase):
    def setUp(self):
        from django.core.cache import cache

        cache.clear()

    def test_registration_rate_limited_after_threshold(self):
        for i in range(10):
            self.client.post(
                reverse("accounts:register"),
                {
                    "phone": f"+25670190{i:04d}", "password": "StrongPass123!",
                    "password_confirm": "StrongPass123!",
                },
            )
        resp = self.client.post(
            reverse("accounts:register"),
            {"phone": "+256701909999", "password": "StrongPass123!", "password_confirm": "StrongPass123!"},
        )
        self.assertEqual(resp.status_code, 429)

    def test_password_reset_request_rate_limited(self):
        for _ in range(5):
            self.client.post(reverse("accounts:password_reset_request"), {"identifier": "+256701910000"})
        resp = self.client.post(reverse("accounts:password_reset_request"), {"identifier": "+256701910000"})
        self.assertEqual(resp.status_code, 429)

    def test_different_ips_not_cross_limited(self):
        for i in range(10):
            self.client.post(
                reverse("accounts:register"),
                {
                    "phone": f"+25670192{i:04d}", "password": "StrongPass123!",
                    "password_confirm": "StrongPass123!",
                },
                REMOTE_ADDR="10.0.0.1",
            )
        resp = self.client.post(
            reverse("accounts:register"),
            {"phone": "+256701929999", "password": "StrongPass123!", "password_confirm": "StrongPass123!"},
            REMOTE_ADDR="10.0.0.2",
        )
        self.assertNotEqual(resp.status_code, 429)


class CSRFEnforcementTests(TestCase):
    def test_login_post_without_csrf_token_rejected(self):
        User.objects.create_user(phone="+256701930000", password="pass12345")
        strict_client = Client(enforce_csrf_checks=True)
        resp = strict_client.post(
            reverse("accounts:login"), {"identifier": "+256701930000", "password": "pass12345"}
        )
        self.assertEqual(resp.status_code, 403)


class RiskEventTests(TestCase):
    def test_login_lockout_records_risk_event(self):
        User.objects.create_user(phone="+256701940000", password="CorrectPass1!")
        for _ in range(6):
            self.client.post(
                reverse("accounts:login"), {"identifier": "+256701940000", "password": "wrong"}
            )
        self.assertTrue(RiskEvent.objects.filter(event_type="login_lockout").exists())

    def test_claim_redemption_lockout_records_risk_event(self):
        # NOTE: redemption_attempts only increments on a call that passes
        # ownership/status/expiry checks — but the very first such call
        # always completes the redemption (flips status to REDEEMED), so
        # every subsequent call short-circuits at the "already redeemed"
        # check *before* reaching the increment. The lockout branch is
        # therefore unreachable via a normal sequential call pattern;
        # this test exercises it directly by pre-seeding the attempt
        # count, which is the honest way to confirm the branch's own
        # logic (lockout + risk event) works, without pretending the
        # increment path is naturally reachable today. Worth revisiting:
        # the real fix is likely a separate "verify code" pre-check step
        # that can fail repeatedly without redeeming, which is what this
        # counter was probably originally meant to guard.
        from claims.models import OfferClaim
        from claims.services import claim_offer, redeem_claim, MAX_REDEMPTION_ATTEMPTS
        from merchants.models import Merchant
        from offers.models import Offer, OfferCategory

        area = Area.objects.create(name="Testville")
        category = OfferCategory.objects.create(key="soap", label="Soap")
        m_user = User.objects.create_user(phone="+256701940001", password="pass12345", role=Role.MERCHANT)
        merchant = Merchant.objects.create(user=m_user, business_name="Shop", category=category, area=area)
        mem_user = User.objects.create_user(phone="+256701940002", password="pass12345", role=Role.MEMBER)
        member = Member.objects.create(user=mem_user, area=area)
        offer = Offer.objects.create(
            merchant=merchant, category=category, area=area, item_name="Soap",
            normal_price=3000, member_price=2500, quantity=1,
            expires_at=timezone.now() + timedelta(days=1), status=Offer.Status.ACTIVE,
        )
        claim = claim_offer(member, offer.id)
        OfferClaim.objects.filter(pk=claim.pk).update(redemption_attempts=MAX_REDEMPTION_ATTEMPTS)

        from claims.services import ClaimError

        with self.assertRaises(ClaimError):
            redeem_claim(merchant, claim.code)
        self.assertTrue(RiskEvent.objects.filter(event_type="claim_redemption_locked").exists())


class IDORSpotCheckTests(TestCase):
    def setUp(self):
        self.area = Area.objects.create(name="Testville")
        self.user_a = User.objects.create_user(phone="+256701950000", password="pass12345", role=Role.MEMBER)
        self.member_a = Member.objects.create(user=self.user_a, area=self.area)
        self.user_b = User.objects.create_user(phone="+256701950001", password="pass12345", role=Role.MEMBER)
        self.member_b = Member.objects.create(user=self.user_b, area=self.area)

    def test_user_cannot_read_another_users_notification(self):
        from notifications.services.dispatch import notify

        notification = notify(self.user_a, "security", "Test", "Message")
        self.client.force_login(self.user_b)
        resp = self.client.post(reverse("notifications:mark_read", args=[notification.id]))
        self.assertEqual(resp.status_code, 404)

    def test_user_cannot_view_another_members_subscription(self):
        from subscriptions.models import SubscriptionPlan
        from subscriptions.services import initiate_renewal

        SubscriptionPlan.objects.create(code="1k-monthly", label="Monthly", price=1000, period_days=30)
        initiate_renewal(self.member_a)

        self.client.force_login(self.user_b)
        resp = self.client.get(reverse("subscriptions:my_subscription"))
        self.assertIsNone(resp.json()["data"])

    def test_user_cannot_cancel_another_members_claim(self):
        from claims.services import claim_offer, cancel_claim, ClaimError
        from merchants.models import Merchant
        from offers.models import Offer, OfferCategory

        category = OfferCategory.objects.create(key="soap", label="Soap")
        m_user = User.objects.create_user(phone="+256701950002", password="pass12345", role=Role.MERCHANT)
        merchant = Merchant.objects.create(user=m_user, business_name="Shop", category=category, area=self.area)
        offer = Offer.objects.create(
            merchant=merchant, category=category, area=self.area, item_name="Soap",
            normal_price=3000, member_price=2500, quantity=5,
            expires_at=timezone.now() + timedelta(days=1), status=Offer.Status.ACTIVE,
        )
        claim = claim_offer(self.member_a, offer.id)
        with self.assertRaises(ClaimError):
            cancel_claim(self.member_b, claim.code)
