from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Role, User
from core.models import Area
from deliveries.models import DeliveryJob, SharedRoute
from deliveries.services import (
    DeliveryError,
    attach_job_to_route,
    cancel_route,
    complete_route,
    create_route,
    publish_route,
    request_delivery,
)
from merchants.models import Merchant
from offers.models import OfferCategory
from riders.models import Rider


class SharedRouteServiceTests(TestCase):
    def setUp(self):
        self.origin = Area.objects.create(name="Origin")
        self.destination = Area.objects.create(name="Destination")
        self.category = OfferCategory.objects.create(key="soap", label="Soap")

        m_user = User.objects.create_user(phone="+256705000000", password="pass12345", role=Role.MERCHANT)
        self.merchant = Merchant.objects.create(
            user=m_user, business_name="Shop", category=self.category, area=self.origin,
        )
        r_user = User.objects.create_user(phone="+256705000001", password="pass12345", role=Role.RIDER)
        self.rider = Rider.objects.create(user=r_user, area=self.origin, status=Rider.Status.VERIFIED)
        self.rider_user = r_user

    def _new_shared_job(self, dropoff_area=None):
        return request_delivery(
            claim=None, merchant=self.merchant, dropoff_area=dropoff_area or self.destination,
            dropoff_address="123 Main St", delivery_type=DeliveryJob.DeliveryType.SHARED_ROUTE, fare=2000,
        )

    def test_create_and_publish_route(self):
        route = create_route(self.rider, self.origin, self.destination, timezone.now() + timedelta(hours=2))
        self.assertEqual(route.status, SharedRoute.Status.DRAFT)
        published = publish_route(self.rider, route.id)
        self.assertEqual(published.status, SharedRoute.Status.PUBLISHED)

    def test_cannot_attach_to_draft_route(self):
        route = create_route(self.rider, self.origin, self.destination, timezone.now() + timedelta(hours=2))
        job = self._new_shared_job()
        with self.assertRaises(DeliveryError):
            attach_job_to_route(self.rider, route.id, job.id)

    def test_attach_matching_job_succeeds(self):
        route = create_route(self.rider, self.origin, self.destination, timezone.now() + timedelta(hours=2))
        publish_route(self.rider, route.id)
        job = self._new_shared_job()
        attached = attach_job_to_route(self.rider, route.id, job.id)
        self.assertEqual(attached.route, route)
        self.assertEqual(attached.status, DeliveryJob.Status.ACCEPTED)
        self.assertEqual(attached.rider, self.rider)

    def test_attach_mismatched_dropoff_area_rejected(self):
        route = create_route(self.rider, self.origin, self.destination, timezone.now() + timedelta(hours=2))
        publish_route(self.rider, route.id)
        other_area = Area.objects.create(name="Somewhere else")
        job = self._new_shared_job(dropoff_area=other_area)
        with self.assertRaises(DeliveryError):
            attach_job_to_route(self.rider, route.id, job.id)

    def test_normal_delivery_type_cannot_attach(self):
        route = create_route(self.rider, self.origin, self.destination, timezone.now() + timedelta(hours=2))
        publish_route(self.rider, route.id)
        job = request_delivery(
            claim=None, merchant=self.merchant, dropoff_area=self.destination, dropoff_address="x",
            delivery_type=DeliveryJob.DeliveryType.NORMAL, fare=1000,
        )
        with self.assertRaises(DeliveryError):
            attach_job_to_route(self.rider, route.id, job.id)

    def test_route_capacity_enforced(self):
        route = create_route(self.rider, self.origin, self.destination, timezone.now() + timedelta(hours=2), max_packages=1)
        publish_route(self.rider, route.id)
        job1 = self._new_shared_job()
        attach_job_to_route(self.rider, route.id, job1.id)
        job2 = self._new_shared_job()
        with self.assertRaises(DeliveryError):
            attach_job_to_route(self.rider, route.id, job2.id)

    def test_cannot_complete_route_with_active_packages(self):
        route = create_route(self.rider, self.origin, self.destination, timezone.now() + timedelta(hours=2))
        publish_route(self.rider, route.id)
        job = self._new_shared_job()
        attach_job_to_route(self.rider, route.id, job.id)
        with self.assertRaises(DeliveryError):
            complete_route(self.rider, route.id)

    def test_complete_route_with_no_active_packages(self):
        route = create_route(self.rider, self.origin, self.destination, timezone.now() + timedelta(hours=2))
        publish_route(self.rider, route.id)
        completed = complete_route(self.rider, route.id)
        self.assertEqual(completed.status, SharedRoute.Status.COMPLETED)

    def test_cancel_route(self):
        route = create_route(self.rider, self.origin, self.destination, timezone.now() + timedelta(hours=2))
        cancelled = cancel_route(self.rider, route.id)
        self.assertEqual(cancelled.status, SharedRoute.Status.CANCELLED)

    def test_other_rider_cannot_publish_someone_elses_route(self):
        route = create_route(self.rider, self.origin, self.destination, timezone.now() + timedelta(hours=2))
        other_user = User.objects.create_user(phone="+256705000002", password="pass12345", role=Role.RIDER)
        other_rider = Rider.objects.create(user=other_user, area=self.origin, status=Rider.Status.VERIFIED)
        with self.assertRaises(DeliveryError):
            publish_route(other_rider, route.id)


class SharedRouteAPITests(TestCase):
    def setUp(self):
        self.origin = Area.objects.create(name="Origin")
        self.destination = Area.objects.create(name="Destination")
        self.category = OfferCategory.objects.create(key="soap", label="Soap")
        m_user = User.objects.create_user(phone="+256705010000", password="pass12345", role=Role.MERCHANT)
        self.merchant = Merchant.objects.create(user=m_user, business_name="Shop", category=self.category, area=self.origin)
        r_user = User.objects.create_user(phone="+256705010001", password="pass12345", role=Role.RIDER)
        self.rider = Rider.objects.create(user=r_user, area=self.origin, status=Rider.Status.VERIFIED)
        self.rider_user = r_user

    def test_full_route_flow_via_api(self):
        self.client.force_login(self.rider_user)
        resp = self.client.post(
            reverse("deliveries:rider_routes"),
            {
                "origin_area_id": self.origin.id, "destination_area_id": self.destination.id,
                "departure_time": (timezone.now() + timedelta(hours=2)).isoformat(), "max_packages": 3,
            },
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 201)
        route_id = resp.json()["data"]["id"]

        resp = self.client.post(reverse("deliveries:publish_route", args=[route_id]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["data"]["status"], "published")

        job = request_delivery(
            claim=None, merchant=self.merchant, dropoff_area=self.destination, dropoff_address="x",
            delivery_type=DeliveryJob.DeliveryType.SHARED_ROUTE, fare=2000,
        )
        resp = self.client.post(reverse("deliveries:attach_job_to_route", args=[route_id, job.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["data"]["status"], "accepted")

    def test_non_rider_forbidden(self):
        member_user = User.objects.create_user(phone="+256705010002", password="pass12345", role=Role.MEMBER)
        self.client.force_login(member_user)
        resp = self.client.get(reverse("deliveries:rider_routes"))
        self.assertEqual(resp.status_code, 403)
