from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from accounts.models import Role, User
from core.models import Area
from members.models import Member
from merchants.models import Merchant
from offers.models import Offer, OfferCategory
from offers.services import expire_stale_offers
from subscriptions.models import Subscription, SubscriptionPlan
from subscriptions.services import expire_stale_subscriptions


class OfferExpiryTests(TestCase):
    def test_expires_only_past_active_offers(self):
        area = Area.objects.create(name="Testville")
        category = OfferCategory.objects.create(key="soap", label="Soap")
        user = User.objects.create_user(phone="+256701800000", password="pass12345", role=Role.MERCHANT)
        merchant = Merchant.objects.create(user=user, business_name="Shop", category=category, area=area)

        expired_offer = Offer.objects.create(
            merchant=merchant, category=category, area=area, item_name="Old",
            normal_price=1000, member_price=800, quantity=1,
            expires_at=timezone.now() + timedelta(hours=1), status=Offer.Status.ACTIVE,
        )
        Offer.objects.filter(pk=expired_offer.pk).update(expires_at=timezone.now() - timedelta(hours=1))

        future_offer = Offer.objects.create(
            merchant=merchant, category=category, area=area, item_name="Fresh",
            normal_price=1000, member_price=800, quantity=1,
            expires_at=timezone.now() + timedelta(days=1), status=Offer.Status.ACTIVE,
        )

        count = expire_stale_offers()
        self.assertEqual(count, 1)
        expired_offer.refresh_from_db()
        future_offer.refresh_from_db()
        self.assertEqual(expired_offer.status, Offer.Status.EXPIRED)
        self.assertEqual(future_offer.status, Offer.Status.ACTIVE)


class SubscriptionExpiryTests(TestCase):
    def test_expires_active_subscription_past_period_end(self):
        area = Area.objects.create(name="Testville")
        plan = SubscriptionPlan.objects.create(code="1k-monthly", label="Monthly", price=1000, period_days=30)
        user = User.objects.create_user(phone="+256701800001", password="pass12345", role=Role.MEMBER)
        member = Member.objects.create(user=user, area=area)

        subscription = Subscription.objects.create(
            member=member, plan=plan, status=Subscription.Status.ACTIVE,
            current_period_start=timezone.now() - timedelta(days=31),
            current_period_end=timezone.now() - timedelta(days=1),
        )

        count = expire_stale_subscriptions()
        self.assertEqual(count, 1)
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, Subscription.Status.EXPIRED)
        self.assertTrue(subscription.events.filter(event_type="expired").exists())

    def test_does_not_touch_still_current_subscription(self):
        area = Area.objects.create(name="Testville")
        plan = SubscriptionPlan.objects.create(code="1k-monthly", label="Monthly", price=1000, period_days=30)
        user = User.objects.create_user(phone="+256701800002", password="pass12345", role=Role.MEMBER)
        member = Member.objects.create(user=user, area=area)

        subscription = Subscription.objects.create(
            member=member, plan=plan, status=Subscription.Status.ACTIVE,
            current_period_start=timezone.now(),
            current_period_end=timezone.now() + timedelta(days=29),
        )
        count = expire_stale_subscriptions()
        self.assertEqual(count, 0)
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, Subscription.Status.ACTIVE)
