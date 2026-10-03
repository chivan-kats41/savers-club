from datetime import timedelta
from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import Role, User
from claims.services import claim_offer
from core.models import Area, SystemSetting
from deliveries.models import DeliveryJob, RiderEarning
from deliveries.services import (
    DeliveryError,
    accept_job,
    confirm_delivery,
    mark_arrived,
    mark_failed,
    mark_on_route,
    mark_picked_up,
    request_delivery,
)
from members.models import Member
from merchants.models import Merchant
from offers.models import Offer, OfferCategory
from riders.models import Rider


class DeliveryFlowTestBase(TestCase):
    def setUp(self):
        self.area = Area.objects.create(name="Testville")
        self.category = OfferCategory.objects.create(key="soap", label="Soap")

        m_user = User.objects.create_user(phone="+256700990000", password="pass12345", role=Role.MERCHANT)
        self.merchant = Merchant.objects.create(
            user=m_user, business_name="Test Shop", category=self.category, area=self.area
        )

        mem_user = User.objects.create_user(phone="+256700990001", password="pass12345", role=Role.MEMBER)
        self.member = Member.objects.create(user=mem_user, area=self.area)

        r_user = User.objects.create_user(phone="+256700990002", password="pass12345", role=Role.RIDER)
        self.rider = Rider.objects.create(user=r_user, area=self.area, status=Rider.Status.VERIFIED)
        self.rider_user = r_user

        self.offer = Offer.objects.create(
            merchant=self.merchant, category=self.category, area=self.area, item_name="Soap",
            normal_price=3000, member_price=2500, quantity=5,
            expires_at=timezone.now() + timedelta(days=1), status=Offer.Status.ACTIVE,
        )
        self.claim = claim_offer(self.member, self.offer.id)

    def _new_job(self, delivery_type=DeliveryJob.DeliveryType.NORMAL, fare=Decimal("1000")):
        return request_delivery(
            claim=self.claim, merchant=self.merchant, dropoff_area=self.area,
            dropoff_address="123 Main St", delivery_type=delivery_type, fare=fare,
        )


class DeliveryServiceTests(DeliveryFlowTestBase):
    def test_full_normal_delivery_flow_no_commission(self):
        job = self._new_job(delivery_type=DeliveryJob.DeliveryType.NORMAL, fare=Decimal("1000"))
        accept_job(self.rider, job.id)
        mark_arrived(self.rider, job.id)
        job, raw_otp = mark_picked_up(self.rider, job.id)
        mark_on_route(self.rider, job.id)
        job = confirm_delivery(self.rider, job.id, raw_otp)

        self.assertEqual(job.status, DeliveryJob.Status.DELIVERED)
        earning = RiderEarning.objects.get(delivery_job=job)
        self.assertEqual(earning.commission_amount, Decimal("0.00"))
        self.assertEqual(earning.net_amount, Decimal("1000.00"))

    def test_shared_route_delivery_applies_commission(self):
        SystemSetting.objects.update_or_create(
            key="delivery.route_commission_percent", defaults={"value": "10.00"}
        )
        job = self._new_job(delivery_type=DeliveryJob.DeliveryType.SHARED_ROUTE, fare=Decimal("2000"))
        accept_job(self.rider, job.id)
        mark_arrived(self.rider, job.id)
        job, raw_otp = mark_picked_up(self.rider, job.id)
        mark_on_route(self.rider, job.id)
        job = confirm_delivery(self.rider, job.id, raw_otp)

        earning = RiderEarning.objects.get(delivery_job=job)
        self.assertEqual(earning.commission_amount, Decimal("200.00"))
        self.assertEqual(earning.net_amount, Decimal("1800.00"))

    def test_cannot_skip_states(self):
        job = self._new_job()
        with self.assertRaises(DeliveryError):
            mark_arrived(self.rider, job.id)  # not yet accepted

    def test_unverified_rider_cannot_accept(self):
        self.rider.status = Rider.Status.PENDING
        self.rider.save()
        job = self._new_job()
        with self.assertRaises(DeliveryError):
            accept_job(self.rider, job.id)

    def test_other_rider_cannot_act_on_job(self):
        job = self._new_job()
        accept_job(self.rider, job.id)

        other_user = User.objects.create_user(phone="+256700990003", password="pass12345", role=Role.RIDER)
        other_rider = Rider.objects.create(user=other_user, area=self.area, status=Rider.Status.VERIFIED)
        with self.assertRaises(DeliveryError):
            mark_arrived(other_rider, job.id)

    def test_wrong_otp_rejected(self):
        job = self._new_job()
        accept_job(self.rider, job.id)
        mark_arrived(self.rider, job.id)
        job, raw_otp = mark_picked_up(self.rider, job.id)
        mark_on_route(self.rider, job.id)
        with self.assertRaises(DeliveryError):
            confirm_delivery(self.rider, job.id, "0000" if raw_otp != "0000" else "1111")

    def test_second_job_on_same_claim_rejected(self):
        self._new_job()
        with self.assertRaises(DeliveryError):
            self._new_job()

    def test_mark_failed_from_active_state(self):
        job = self._new_job()
        accept_job(self.rider, job.id)
        job = mark_failed(self.rider, job.id, "Customer unreachable")
        self.assertEqual(job.status, DeliveryJob.Status.FAILED)
        self.assertEqual(job.failure_reason, "Customer unreachable")


class DeliveryAPITests(DeliveryFlowTestBase):
    @override_settings(DEBUG=True)
    def test_rider_full_flow_via_api(self):
        job = self._new_job()
        self.client.force_login(self.rider_user)

        resp = self.client.post(reverse("deliveries:accept_job", args=[job.id]))
        self.assertEqual(resp.status_code, 200)

        resp = self.client.post(reverse("deliveries:arrived_job", args=[job.id]))
        self.assertEqual(resp.status_code, 200)

        resp = self.client.post(reverse("deliveries:picked_up_job", args=[job.id]))
        self.assertEqual(resp.status_code, 200)
        otp = resp.json()["data"].get("dev_only_otp")
        self.assertIsNotNone(otp)

        resp = self.client.post(reverse("deliveries:on_route_job", args=[job.id]))
        self.assertEqual(resp.status_code, 200)

        resp = self.client.post(
            reverse("deliveries:delivered_job", args=[job.id]), {"otp": otp}, content_type="application/json"
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["data"]["status"], "delivered")

    def test_non_rider_cannot_accept(self):
        job = self._new_job()
        self.client.force_login(self.member.user)
        resp = self.client.post(reverse("deliveries:accept_job", args=[job.id]))
        self.assertEqual(resp.status_code, 403)

    def test_rider_earnings_endpoint(self):
        job = self._new_job(fare=Decimal("1500"))
        accept_job(self.rider, job.id)
        mark_arrived(self.rider, job.id)
        job, raw_otp = mark_picked_up(self.rider, job.id)
        mark_on_route(self.rider, job.id)
        confirm_delivery(self.rider, job.id, raw_otp)

        self.client.force_login(self.rider_user)
        resp = self.client.get(reverse("deliveries:rider_earnings"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Decimal(resp.json()["data"]["totals"]["net"]), Decimal("1500.00"))
