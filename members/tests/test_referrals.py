from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Role, User
from core.models import Area, SystemSetting
from members.models import Member, ReferralReward
from subscriptions.models import SubscriptionPlan
from subscriptions.services import confirm_payment, initiate_renewal


class RegistrationCreatesMemberTests(TestCase):
    """The gap this phase fixed: registration previously created a User
    but never a Member profile, which would 404 every membership-scoped
    endpoint for a real new signup."""

    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        self.area = Area.objects.create(name="Testville")

    def test_registration_creates_member_profile(self):
        self.client.post(
            reverse("accounts:register"),
            {
                "phone": "+256702100000", "area": self.area.id,
                "password": "StrongPass123!", "password_confirm": "StrongPass123!",
            },
        )
        user = User.objects.get(phone="+256702100000")
        self.assertTrue(Member.objects.filter(user=user, area=self.area).exists())

    def test_registration_without_area_rejected(self):
        resp = self.client.post(
            reverse("accounts:register"),
            {
                "phone": "+256702100001",
                "password": "StrongPass123!", "password_confirm": "StrongPass123!",
            },
        )
        self.assertEqual(resp.status_code, 200)  # re-renders form with error
        self.assertFalse(User.objects.filter(phone="+256702100001").exists())

    def test_registration_with_referral_code_links_referrer(self):
        referrer_user = User.objects.create_user(phone="+256702100002", password="pass12345", role=Role.MEMBER)
        referrer = Member.objects.create(user=referrer_user, area=self.area)

        self.client.post(
            reverse("accounts:register"),
            {
                "phone": "+256702100003", "area": self.area.id,
                "referral_code": referrer.referral_code,
                "password": "StrongPass123!", "password_confirm": "StrongPass123!",
            },
        )
        new_user = User.objects.get(phone="+256702100003")
        new_member = Member.objects.get(user=new_user)
        self.assertEqual(new_member.referred_by, referrer)

    def test_registration_with_invalid_referral_code_still_succeeds(self):
        self.client.post(
            reverse("accounts:register"),
            {
                "phone": "+256702100004", "area": self.area.id,
                "referral_code": "NOTREAL1",
                "password": "StrongPass123!", "password_confirm": "StrongPass123!",
            },
        )
        user = User.objects.get(phone="+256702100004")
        member = Member.objects.get(user=user)
        self.assertIsNone(member.referred_by)


class ReferralRewardTriggerTests(TestCase):
    def setUp(self):
        SystemSetting.objects.update_or_create(key="referral.reward_ugx", defaults={"value": "500"})
        self.area = Area.objects.create(name="Testville")
        self.plan = SubscriptionPlan.objects.create(code="1k-monthly", label="Monthly", price=1000, period_days=30)

        referrer_user = User.objects.create_user(phone="+256702110000", password="pass12345", role=Role.MEMBER)
        self.referrer = Member.objects.create(user=referrer_user, area=self.area)

        referred_user = User.objects.create_user(phone="+256702110001", password="pass12345", role=Role.MEMBER)
        self.referred = Member.objects.create(user=referred_user, area=self.area, referred_by=self.referrer)

    def test_first_activation_creates_reward(self):
        payment = initiate_renewal(self.referred)
        confirm_payment(payment, success=True)
        reward = ReferralReward.objects.get(referred_member=self.referred)
        self.assertEqual(reward.referrer, self.referrer)
        self.assertEqual(reward.amount, 500)
        self.assertEqual(reward.status, ReferralReward.Status.PENDING)

    def test_no_reward_when_no_referrer(self):
        unreferred_user = User.objects.create_user(phone="+256702110002", password="pass12345", role=Role.MEMBER)
        unreferred = Member.objects.create(user=unreferred_user, area=self.area)
        payment = initiate_renewal(unreferred)
        confirm_payment(payment, success=True)
        self.assertFalse(ReferralReward.objects.filter(referred_member=unreferred).exists())

    def test_second_renewal_does_not_create_second_reward(self):
        payment = initiate_renewal(self.referred)
        confirm_payment(payment, success=True)
        self.assertEqual(ReferralReward.objects.filter(referred_member=self.referred).count(), 1)

        # Second renewal cycle for the same member.
        payment2 = initiate_renewal(self.referred)
        confirm_payment(payment2, success=True)
        self.assertEqual(ReferralReward.objects.filter(referred_member=self.referred).count(), 1)

    def test_failed_first_payment_creates_no_reward(self):
        payment = initiate_renewal(self.referred)
        confirm_payment(payment, success=False)
        self.assertFalse(ReferralReward.objects.filter(referred_member=self.referred).exists())

    def test_self_referral_rejected(self):
        with self.assertRaises(Exception):
            ReferralReward.objects.create(referrer=self.referrer, referred_member=self.referrer, amount=500)


class MyReferralsAPITests(TestCase):
    def setUp(self):
        self.area = Area.objects.create(name="Testville")
        self.plan = SubscriptionPlan.objects.create(code="1k-monthly", label="Monthly", price=1000, period_days=30)
        referrer_user = User.objects.create_user(phone="+256702120000", password="pass12345", role=Role.MEMBER)
        self.referrer = Member.objects.create(user=referrer_user, area=self.area)
        self.referrer_user = referrer_user

        referred_user = User.objects.create_user(phone="+256702120001", password="pass12345", role=Role.MEMBER)
        self.referred = Member.objects.create(user=referred_user, area=self.area, referred_by=self.referrer)

    def test_my_referrals_shows_code_and_rewards(self):
        payment = initiate_renewal(self.referred)
        confirm_payment(payment, success=True)

        self.client.force_login(self.referrer_user)
        resp = self.client.get(reverse("members:my_referrals"))
        data = resp.json()["data"]
        self.assertEqual(data["referral_code"], self.referrer.referral_code)
        self.assertEqual(data["referred_count"], 1)
        self.assertEqual(data["pending_reward_total"], "500")
