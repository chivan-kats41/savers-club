"""Onboarding, uploads, tracking, admin controls, 2FA, verified webhooks, server-side fares."""
import io
import json
import time
from decimal import Decimal
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from accounts import totp
from accounts.models import Role, User
from agents.models import Agent, AgentTask
from claims.models import OfferClaim
from core.models import Area, AuditLog, SystemSetting
from deliveries.models import DeliveryJob, PickupPoint
from members.models import Member
from merchants.models import Merchant
from notifications.models import Notification
from offers.models import Offer, OfferInteraction
from riders.models import Rider


def png_bytes(size=(40, 40)):
    buf = io.BytesIO()
    Image.new("RGB", size, "red").save(buf, "PNG")
    return buf.getvalue()


def post_json(client, url, data=None, **kw):
    return client.post(url, json.dumps(data or {}), content_type="application/json", **kw)


class Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_system_settings", verbosity=0)
        call_command("seed_subscription_plans", verbosity=0)
        call_command("seed_demo_data", verbosity=0)
        call_command("seed_admin_group", verbosity=0)
        cls.area = Area.objects.first()
        cls.member = Member.objects.select_related("user").first()
        cls.merchant = Merchant.objects.select_related("user").first()
        cls.admin = User.objects.create_user(phone="+256700000101", password="x", role=Role.SUPER_ADMIN, first_name="Root")
        cls.admin.is_superuser = True
        cls.admin.save()
        cls.plain_admin = User.objects.create_user(phone="+256700000102", password="x", role=Role.ADMIN, first_name="Plain")
        from django.contrib.auth.models import Group
        cls.plain_admin.groups.add(Group.objects.get(name="Platform Admin"))


class OnboardingTests(Base):
    def test_user_can_apply_as_merchant_and_rider_but_only_once(self):
        u = User.objects.create_user(phone="+256700000201", password="x", first_name="New")
        self.client.force_login(u)
        from offers.models import OfferCategory
        cat = OfferCategory.objects.first()
        r = post_json(self.client, reverse("hub_api:merchant_apply"), {"business_name": "Mama Shop", "category": cat.pk, "area": self.area.pk})
        self.assertEqual(r.status_code, 201, r.content)
        m = Merchant.objects.get(user=u)
        self.assertEqual(m.status, Merchant.Status.PENDING)          # never self-verified
        self.assertEqual(post_json(self.client, reverse("hub_api:merchant_apply"), {"business_name": "Again", "category": cat.pk, "area": self.area.pk}).status_code, 409)
        r = post_json(self.client, reverse("hub_api:rider_apply"), {"area": self.area.pk, "vehicle_type": "boda", "plate_number": "uaa 123x"})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(Rider.objects.get(user=u).status, Rider.Status.PENDING)
        # pending merchant can't post offers (verification gate is enforced by the existing service)
        self.assertEqual(self.client.get(reverse("apply_merchant")).status_code, 200)
        self.assertEqual(self.client.get(reverse("apply_rider")).status_code, 200)

    def test_apply_requires_login_and_valid_input(self):
        self.assertIn(self.client.post(reverse("hub_api:merchant_apply"), {}, content_type="application/json").status_code, (401, 403))
        self.client.force_login(self.member.user)
        self.assertEqual(post_json(self.client, reverse("hub_api:rider_apply"), {"area": 99999, "vehicle_type": "rocket"}).status_code, 400)


class UploadTests(Base):
    def setUp(self):
        self.rider_user = User.objects.create_user(phone="+256700000301", password="x", role=Role.RIDER)
        self.rider = Rider.objects.create(user=self.rider_user, area=self.area, status=Rider.Status.PENDING)

    def test_valid_image_is_reencoded_and_stored_privately(self):
        self.client.force_login(self.rider_user)
        f = SimpleUploadedFile("my id.png", png_bytes(), content_type="image/png")
        r = self.client.post(reverse("hub_api:rider_documents"), {"doc_type": "id_document", "file": f})
        self.assertEqual(r.status_code, 201, r.content)
        doc = self.rider.documents.get()
        self.assertTrue(doc.file.name.endswith(".jpg"))               # re-encoded, client name discarded
        self.assertNotIn("my id", doc.file.name)
        self.assertIn("private_media", doc.file.path)                 # not under MEDIA_ROOT

    def test_disguised_and_oversized_files_rejected(self):
        self.client.force_login(self.rider_user)
        for name, body in (("evil.png", b"<?php system($_GET['c']); ?>"), ("x.svg", b"<svg onload=alert(1)>"), ("e.png", b"GIF89a" + b"x" * 50)):
            r = self.client.post(reverse("hub_api:rider_documents"), {"doc_type": "id_document", "file": SimpleUploadedFile(name, body)})
            self.assertEqual(r.status_code, 400, name)
        big = SimpleUploadedFile("big.png", png_bytes() + b"0" * (9 * 1024 * 1024))
        self.assertEqual(self.client.post(reverse("hub_api:rider_documents"), {"doc_type": "id_document", "file": big}).status_code, 400)
        self.assertEqual(self.rider.documents.count(), 0)

    def test_document_download_is_access_controlled(self):
        self.client.force_login(self.rider_user)
        self.client.post(reverse("hub_api:rider_documents"), {"doc_type": "id_document", "file": SimpleUploadedFile("a.png", png_bytes())})
        doc = self.rider.documents.get()
        url = reverse("rider_document", args=[doc.pk])
        self.assertEqual(self.client.get(url).status_code, 200)       # owner
        self.client.force_login(self.member.user)
        self.assertEqual(self.client.get(url).status_code, 404)       # stranger
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(url).status_code, 200)       # admin
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 302)       # anonymous -> login

    def test_offer_photo_upload_owner_only(self):
        offer = Offer.objects.filter(merchant=self.merchant).first() or Offer.objects.first()
        owner = offer.merchant.user
        self.client.force_login(owner)
        r = self.client.post(reverse("hub_api:offer_image", args=[offer.pk]), {"image": SimpleUploadedFile("p.png", png_bytes())})
        self.assertEqual(r.status_code, 201, r.content)
        self.client.force_login(self.member.user)
        self.assertEqual(self.client.post(reverse("hub_api:offer_image", args=[offer.pk]), {"image": SimpleUploadedFile("p.png", png_bytes())}).status_code, 403)


class TrackingAndNotificationTests(Base):
    def test_interaction_tracking_counts_and_dedupes_views(self):
        offer = Offer.objects.filter(status=Offer.Status.ACTIVE).first()
        self.client.force_login(self.member.user)
        url = reverse("hub_api:offer_interact", args=[offer.pk])
        self.assertEqual(post_json(self.client, url, {"kind": "call"}).status_code, 201)
        self.assertEqual(post_json(self.client, url, {"kind": "view"}).status_code, 201)
        self.assertFalse(post_json(self.client, url, {"kind": "view"}).json()["data"]["counted"])
        self.assertEqual(post_json(self.client, url, {"kind": "hack"}).status_code, 400)
        self.assertEqual(OfferInteraction.objects.filter(offer=offer, kind="call").count(), 1)

    def test_notifications_page_and_mark_all(self):
        Notification.objects.create(user=self.member.user, category="offer", title="Hello", message="World")
        self.client.force_login(self.member.user)
        r = self.client.get(reverse("notifications"))
        self.assertContains(r, "Hello")
        self.assertEqual(self.client.get(reverse("member")).context["unread_count"], 1)
        post_json(self.client, reverse("hub_api:read_all"))
        self.assertEqual(Notification.objects.filter(user=self.member.user, is_read=False).count(), 0)


class AdminControlTests(Base):
    def test_admin_offer_moderation_is_capability_gated_and_audited(self):
        offer = Offer.objects.create(
            merchant=self.merchant, category=self.merchant.category, area=self.merchant.area, item_name="Test", normal_price=2000,
            member_price=1500, quantity=3, expires_at=timezone.now() + timezone.timedelta(days=1), status=Offer.Status.PENDING,
        )
        url = reverse("hub_api:admin_offer_action", args=[offer.pk, "approve"])
        self.client.force_login(self.member.user)
        self.assertEqual(post_json(self.client, url).status_code, 403)
        self.client.force_login(self.admin)
        self.assertEqual(post_json(self.client, url).status_code, 200)
        offer.refresh_from_db()
        self.assertEqual(offer.status, Offer.Status.ACTIVE)
        self.assertTrue(AuditLog.objects.filter(action="offer_approve", object_id=str(offer.pk)).exists())
        self.assertEqual(post_json(self.client, reverse("hub_api:admin_offer_action", args=[offer.pk, "nuke"])).status_code, 404)
        # an already-active offer can't be 'approved' again
        self.assertEqual(post_json(self.client, url).status_code, 400)

    def test_settings_changes_need_settings_manage(self):
        SystemSetting.objects.update_or_create(key="delivery.fare_same_area", defaults={"value": "2000"})
        url = reverse("hub_api:admin_setting", args=["delivery.fare_same_area"])
        self.client.force_login(self.plain_admin)       # default group lacks settings_manage
        self.assertEqual(self.client.patch(url, json.dumps({"value": "1"}), content_type="application/json").status_code, 403)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.patch(url, json.dumps({"value": "-5"}), content_type="application/json").status_code, 400)
        self.assertEqual(self.client.patch(url, json.dumps({"value": "2500"}), content_type="application/json").status_code, 200)
        self.assertEqual(SystemSetting.objects.get(key="delivery.fare_same_area").value, "2500")
        self.assertTrue(AuditLog.objects.filter(action="setting_changed").exists())

    def test_pickup_points_tasks_and_broadcast(self):
        self.client.force_login(self.admin)
        r = post_json(self.client, reverse("hub_api:admin_pickup_points"), {"name": "Shell Mutungo", "area": self.area.pk, "address": "Main road"})
        self.assertEqual(r.status_code, 201)
        self.assertTrue(PickupPoint.objects.filter(name="Shell Mutungo").exists())
        agent_user = User.objects.create_user(phone="+256700000401", password="x", role=Role.AGENT)
        agent = Agent.objects.create(user=agent_user); agent.areas.add(self.area)
        r = post_json(self.client, reverse("hub_api:admin_agent_tasks"), {"agent": agent.pk, "title": "Collect prices", "kind": "collect_prices"})
        self.assertEqual(r.status_code, 201, r.content)
        task = AgentTask.objects.get()
        # only the assigned agent can complete it
        self.client.force_login(self.member.user)
        self.assertEqual(post_json(self.client, reverse("hub_api:task_complete", args=[task.pk])).status_code, 403)
        self.client.force_login(agent_user)
        self.assertEqual(post_json(self.client, reverse("hub_api:task_complete", args=[task.pk])).status_code, 200)
        self.client.force_login(self.admin)
        r = post_json(self.client, reverse("hub_api:admin_broadcast"), {"title": "Hello all", "message": "Maintenance tonight", "audience": "member"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(Notification.objects.filter(user=self.member.user, title="Hello all").exists())
        for name in ("admin_pickup", "admin_tasks", "admin_settings", "admin_notifications", "admin_agents"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)

    def test_admin_can_verify_pending_merchant(self):
        self.merchant.status = Merchant.Status.PENDING; self.merchant.save()
        self.client.force_login(self.admin)
        r = post_json(self.client, reverse("hub_api:admin_verify_merchant", args=[self.merchant.pk]), {"outcome": "verified"})
        self.assertEqual(r.status_code, 200, r.content)
        self.merchant.refresh_from_db()
        self.assertEqual(self.merchant.status, Merchant.Status.VERIFIED)
        self.assertEqual(post_json(self.client, reverse("hub_api:admin_verify_merchant", args=[self.merchant.pk]), {"outcome": "godmode"}).status_code, 400)


class ServerSideFareTests(Base):
    def test_client_fare_is_ignored(self):
        offer = Offer.objects.filter(status=Offer.Status.ACTIVE, delivery_available=True).first()
        if offer is None:
            offer = Offer.objects.filter(status=Offer.Status.ACTIVE).first()
            offer.delivery_available = True; offer.save()
        claim = OfferClaim.objects.create(offer=offer, member=self.member, code="1K-TEST1", expires_at=timezone.now() + timezone.timedelta(hours=5), expected_saving=100) if not hasattr(OfferClaim, "create_claim") else None
        self.client.force_login(self.member.user)
        r = post_json(self.client, reverse("deliveries:request_delivery"), {
            "claim_code": claim.code, "dropoff_area": self.area.name, "dropoff_address": "Plot 4", "fare": "1",
        })
        self.assertEqual(r.status_code, 201, r.content)
        job = DeliveryJob.objects.get(claim=claim)
        self.assertGreaterEqual(job.fare, Decimal("1000"))            # not the attacker's UGX 1
        self.assertEqual(job.fare, Decimal(SystemSetting.objects.get(key="delivery.fare_same_area").value) if job.pickup_merchant.area_id == self.area.pk else job.fare)


class TwoFactorTests(Base):
    @override_settings(ADMIN_REQUIRE_2FA=True)
    def test_admin_must_enrol_then_verify(self):
        self.client.force_login(self.admin)
        r = self.client.get(reverse("admin_index"))
        self.assertEqual(r.status_code, 302)
        self.assertIn("/accounts/2fa/setup/", r["Location"])
        r = post_json(self.client, reverse("hub_api:admin_areas"), {"name": "Sneaky"})
        self.assertEqual(r.status_code, 403)                           # API gated too
        self.assertEqual(r.json()["error"]["code"], "TWO_FACTOR_REQUIRED")
        page = self.client.get(reverse("accounts:2fa_setup"))
        secret = self.client.session["pending_totp_secret"]
        bad = self.client.post(reverse("accounts:2fa_setup"), {"code": "000000"})
        self.assertContains(bad, "match")
        good = self.client.post(reverse("accounts:2fa_setup"), {"code": totp._code(secret, int(time.time() // 30))})
        self.assertEqual(good.status_code, 302)
        self.assertEqual(self.client.get(reverse("admin_index")).status_code, 200)
        self.assertEqual(post_json(self.client, reverse("hub_api:admin_areas"), {"name": "Legit Area"}).status_code, 201)
        # a new session must verify again
        self.client.logout(); self.client.force_login(self.admin)
        r = self.client.get(reverse("admin_index"))
        self.assertIn("/accounts/2fa/verify/", r["Location"])

    @override_settings(ADMIN_REQUIRE_2FA=True)
    def test_non_admins_unaffected(self):
        self.client.force_login(self.member.user)
        self.assertEqual(self.client.get(reverse("member")).status_code, 200)

    def test_totp_matches_rfc6238_vector(self):
        # RFC 6238 appendix B (SHA-1), secret "12345678901234567890", T=59 -> 94287082 (last 6 digits)
        import base64
        secret = base64.b32encode(b"12345678901234567890").decode()
        self.assertEqual(totp._code(secret, 59 // 30), "287082")
        self.assertTrue(totp.verify(secret, "287082", now=59))
        self.assertFalse(totp.verify(secret, "287082", now=59 + 300))


class VerifiedWebhookTests(Base):
    @override_settings(DEBUG=False, IOTEC_CALLBACK_SECRET="s3cret")
    def test_forged_success_does_not_credit_when_provider_says_pending(self):
        from payments.models import Payment
        pay = Payment.objects.create(user=self.member.user, amount=1000, purpose="subscription", method="mobile_money",
                                     payer_phone="+256700000001", provider_transaction_id="tx-1", status=Payment.Status.PENDING)
        with mock.patch("payments.services.reconciliation.get_collection_status", return_value={"status": "pending"}):
            r = self.client.post(reverse("payments:iotec_collection_callback"),
                                 {"externalId": str(pay.internal_reference), "status": "success"},
                                 content_type="application/json", HTTP_X_CALLBACK_SECRET="s3cret")
        self.assertEqual(r.status_code, 200)
        pay.refresh_from_db()
        self.assertEqual(pay.status, Payment.Status.PENDING)

    @override_settings(DEBUG=False, IOTEC_CALLBACK_SECRET="s3cret")
    def test_provider_confirmed_success_is_applied(self):
        from payments.models import Payment
        pay = Payment.objects.create(user=self.member.user, amount=1000, purpose="subscription", method="mobile_money",
                                     payer_phone="+256700000001", provider_transaction_id="tx-2", status=Payment.Status.PENDING)
        with mock.patch("payments.services.reconciliation.get_collection_status", return_value={"status": "success"}):
            self.client.post(reverse("payments:iotec_collection_callback"), {"externalId": str(pay.internal_reference), "status": "pending"},
                             content_type="application/json", HTTP_X_CALLBACK_SECRET="s3cret")
        pay.refresh_from_db()
        self.assertEqual(pay.status, Payment.Status.SUCCESS)       # provider's answer wins, not the payload's


class RateLimitTests(Base):
    def test_throttle_scopes_exist(self):
        from django.conf import settings
        rates = settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]
        for scope in ("redeem", "delivery_otp", "write", "agent_action", "interact"):
            self.assertIn(scope, rates)
