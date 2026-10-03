from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from accounts.models import Role, User
from core.models import Area
from notifications.models import Notification, NotificationPreference
from notifications.services.dispatch import notify


class DispatchTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(phone="+256701700000", email="u@example.com", password="pass12345")

    def test_notify_creates_in_app_row(self):
        notification = notify(self.user, "security", "Test", "Something happened")
        self.assertTrue(Notification.objects.filter(pk=notification.pk).exists())

    @patch("notifications.tasks.send_sms")
    @patch("notifications.tasks.send_email_notification")
    def test_dispatch_respects_disabled_sms_preference(self, mock_email, mock_sms):
        NotificationPreference.objects.create(user=self.user, sms_enabled=False, email_enabled=True)
        notify(self.user, "security", "Test", "Message")
        mock_sms.assert_not_called()
        mock_email.assert_called_once()

    @patch("notifications.tasks.send_sms")
    @patch("notifications.tasks.send_email_notification")
    def test_dispatch_sends_both_by_default(self, mock_email, mock_sms):
        notify(self.user, "security", "Test", "Message")
        mock_sms.assert_called_once()
        mock_email.assert_called_once()

    def test_missing_notification_id_is_a_noop(self):
        from notifications.tasks import dispatch_external_notification

        # Should not raise even for a nonexistent id.
        dispatch_external_notification(999999)


class NotificationAPITests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(phone="+256701710000", password="pass12345")

    def test_list_own_notifications(self):
        notify(self.user, "security", "Test", "Message")
        self.client.force_login(self.user)
        resp = self.client.get(reverse("notifications:my_notifications"))
        self.assertEqual(len(resp.json()["data"]), 1)

    def test_mark_read(self):
        notification = notify(self.user, "security", "Test", "Message")
        self.client.force_login(self.user)
        resp = self.client.post(reverse("notifications:mark_read", args=[notification.id]))
        self.assertTrue(resp.json()["data"]["is_read"])

    def test_cannot_mark_another_users_notification_read(self):
        other = User.objects.create_user(phone="+256701710001", password="pass12345")
        notification = notify(other, "security", "Test", "Message")
        self.client.force_login(self.user)
        resp = self.client.post(reverse("notifications:mark_read", args=[notification.id]))
        self.assertEqual(resp.status_code, 404)

    def test_update_preferences(self):
        self.client.force_login(self.user)
        resp = self.client.patch(
            reverse("notifications:preferences"), {"sms_enabled": False}, content_type="application/json"
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["data"]["sms_enabled"])


class NotificationWiringTests(TestCase):
    """Confirms notify() actually fires from the flows it was wired into."""

    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        self.area = Area.objects.create(name="Testville")

    def test_registration_sends_notification(self):
        resp = self.client.post(
            reverse("accounts:register"),
            {
                "phone": "+256701720000", "email": "new@example.com",
                "area": self.area.id,
                "password": "StrongPass123!", "password_confirm": "StrongPass123!",
            },
        )
        user = User.objects.get(phone="+256701720000")
        self.assertTrue(Notification.objects.filter(user=user, category="registration").exists())

    def test_claim_redemption_sends_notification(self):
        from datetime import timedelta

        from django.utils import timezone

        from claims.services import claim_offer, redeem_claim
        from members.models import Member
        from merchants.models import Merchant
        from offers.models import Offer, OfferCategory

        area = self.area
        category = OfferCategory.objects.create(key="soap", label="Soap")
        m_user = User.objects.create_user(phone="+256701720001", password="pass12345", role=Role.MERCHANT)
        merchant = Merchant.objects.create(user=m_user, business_name="Shop", category=category, area=area)
        mem_user = User.objects.create_user(phone="+256701720002", password="pass12345", role=Role.MEMBER)
        member = Member.objects.create(user=mem_user, area=area)
        offer = Offer.objects.create(
            merchant=merchant, category=category, area=area, item_name="Soap",
            normal_price=3000, member_price=2500, quantity=5,
            expires_at=timezone.now() + timedelta(days=1), status=Offer.Status.ACTIVE,
        )
        claim = claim_offer(member, offer.id)
        redeem_claim(merchant, claim.code)
        self.assertTrue(Notification.objects.filter(user=mem_user, category="claim").exists())


class BrokerOutageResilienceTests(TestCase):
    """CELERY_TASK_ALWAYS_EAGER=True in the testing settings means every
    other test in this suite bypasses the broker entirely — this test
    exists specifically to cover the case eager execution hides: a
    real broker-connection failure must never break the caller. Found
    via manual smoke-testing (not the automated suite) that notify()
    calls throughout the app — registration, claim redemption, payment
    callbacks, delivery events — would 500 the entire request if Redis
    was unreachable, before this test/fix existed."""

    def test_notify_survives_broker_connection_error(self):
        from unittest.mock import patch

        user = User.objects.create_user(phone="+256701730000", password="pass12345")

        with patch("notifications.tasks.dispatch_external_notification.delay", side_effect=ConnectionError("no broker")):
            # Must not raise — the in-app row still gets created even
            # though queueing the SMS/email leg failed.
            notification = notify(user, "security", "Test", "Message")

        self.assertTrue(Notification.objects.filter(pk=notification.pk).exists())
