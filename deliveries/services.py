from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from core.services import route_commission_percent
from riders.models import Rider

from .models import DeliveryJob, DeliveryOTP, DeliveryStatusHistory, RiderEarning, SharedRoute


class DeliveryError(ValidationError):
    pass


def _transition(job: DeliveryJob, to_status: str, actor=None, notes: str = "", **field_updates):
    from_status = job.status
    job.status = to_status
    for field, value in field_updates.items():
        setattr(job, field, value)
    job.save(update_fields=["status", *field_updates.keys()])
    DeliveryStatusHistory.objects.create(
        job=job, from_status=from_status, to_status=to_status, changed_by=actor, notes=notes
    )


def compute_fare(merchant, dropoff_area, delivery_type: str) -> Decimal:
    """The platform, not the member, decides the fare. Prices come from
    SystemSetting so an admin can tune them without a deploy."""
    from core.services import get_setting_decimal

    if delivery_type == DeliveryJob.DeliveryType.SHARED_ROUTE:
        return get_setting_decimal("delivery.fare_shared_route", Decimal("2000"))
    if merchant.area_id == dropoff_area.pk:
        return get_setting_decimal("delivery.fare_same_area", Decimal("2000"))
    return get_setting_decimal("delivery.fare_cross_area", Decimal("4000"))


@transaction.atomic
def request_delivery(claim, merchant, dropoff_area, dropoff_address: str, delivery_type: str, fare: Decimal) -> DeliveryJob:
    if hasattr(claim, "delivery_job"):
        raise DeliveryError("A delivery has already been requested for this claim.")
    if fare is None or fare <= 0:
        raise DeliveryError("Delivery fare must be positive.")

    job = DeliveryJob.objects.create(
        claim=claim,
        pickup_merchant=merchant,
        dropoff_area=dropoff_area,
        dropoff_address=dropoff_address,
        delivery_type=delivery_type,
        fare=fare,
        status=DeliveryJob.Status.REQUESTED,
    )
    DeliveryStatusHistory.objects.create(job=job, from_status="", to_status=job.status)
    return job


@transaction.atomic
def accept_job(rider: Rider, job_id: int) -> DeliveryJob:
    if rider.status != Rider.Status.VERIFIED:
        raise DeliveryError("Only verified riders can accept delivery jobs.")

    try:
        job = DeliveryJob.objects.select_for_update().get(pk=job_id)
    except DeliveryJob.DoesNotExist as exc:
        raise DeliveryError("Delivery job not found.") from exc

    if job.status != DeliveryJob.Status.REQUESTED:
        raise DeliveryError("This job is no longer available.")

    _transition(job, DeliveryJob.Status.ACCEPTED, actor=rider.user, rider=rider, assigned_at=timezone.now())
    return job


def _owned_active_job(rider: Rider, job_id: int, expected_status: str) -> DeliveryJob:
    try:
        job = DeliveryJob.objects.select_for_update().get(pk=job_id)
    except DeliveryJob.DoesNotExist as exc:
        raise DeliveryError("Delivery job not found.") from exc
    if job.rider_id != rider.id:
        raise DeliveryError("This job is not assigned to you.")
    if job.status != expected_status:
        raise DeliveryError(f"Job must be {expected_status} for this action (currently {job.status}).")
    return job


@transaction.atomic
def mark_arrived(rider: Rider, job_id: int) -> DeliveryJob:
    job = _owned_active_job(rider, job_id, DeliveryJob.Status.ACCEPTED)
    _transition(job, DeliveryJob.Status.ARRIVED_AT_SELLER, actor=rider.user)
    return job


@transaction.atomic
def mark_picked_up(rider: Rider, job_id: int) -> tuple[DeliveryJob, str]:
    job = _owned_active_job(rider, job_id, DeliveryJob.Status.ARRIVED_AT_SELLER)
    _transition(job, DeliveryJob.Status.PICKED_UP, actor=rider.user, picked_up_at=timezone.now())
    _, raw_otp = DeliveryOTP.issue(job)
    return job, raw_otp


@transaction.atomic
def mark_on_route(rider: Rider, job_id: int) -> DeliveryJob:
    job = _owned_active_job(rider, job_id, DeliveryJob.Status.PICKED_UP)
    _transition(job, DeliveryJob.Status.ON_ROUTE, actor=rider.user)
    return job


@transaction.atomic
def confirm_delivery(rider: Rider, job_id: int, otp_code: str) -> DeliveryJob:
    job = _owned_active_job(rider, job_id, DeliveryJob.Status.ON_ROUTE)

    try:
        otp = DeliveryOTP.objects.select_for_update().get(job=job)
    except DeliveryOTP.DoesNotExist as exc:
        raise DeliveryError("No delivery code was issued for this job.") from exc

    if not otp.verify_code(otp_code):
        raise DeliveryError("Invalid or expired delivery code.")

    _transition(job, DeliveryJob.Status.DELIVERED, actor=rider.user, delivered_at=timezone.now())

    gross = job.fare
    commission_pct = (
        route_commission_percent() if job.delivery_type == DeliveryJob.DeliveryType.SHARED_ROUTE else Decimal("0")
    )
    commission = (gross * commission_pct / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    net = gross - commission

    RiderEarning.objects.create(
        rider=rider, delivery_job=job, gross_amount=gross, commission_amount=commission, net_amount=net
    )

    if job.claim_id:
        from notifications.services.dispatch import notify

        notify(
            job.claim.member.user, "delivery", "Delivered!",
            f"Your order from {job.pickup_merchant.business_name} has been delivered.",
        )

    return job


@transaction.atomic
def mark_failed(rider: Rider, job_id: int, reason: str) -> DeliveryJob:
    try:
        job = DeliveryJob.objects.select_for_update().get(pk=job_id)
    except DeliveryJob.DoesNotExist as exc:
        raise DeliveryError("Delivery job not found.") from exc
    if job.rider_id != rider.id:
        raise DeliveryError("This job is not assigned to you.")
    if job.status not in DeliveryJob.ACTIVE_STATUSES:
        raise DeliveryError("Job is not in an active state.")

    _transition(
        job, DeliveryJob.Status.FAILED, actor=rider.user, notes=reason,
        failed_at=timezone.now(), failure_reason=reason[:255],
    )

    if job.claim_id:
        from notifications.services.dispatch import notify

        notify(
            job.claim.member.user, "delivery", "Delivery failed",
            f"Your delivery from {job.pickup_merchant.business_name} could not be completed: {reason}",
        )

    return job


# ---------------------------------------------------------------------------
# SharedRoute — the grouping layer. Individual job state transitions above
# are untouched; these functions only manage route lifecycle and which
# jobs are attached to a route.
# ---------------------------------------------------------------------------

@transaction.atomic
def create_route(rider, origin_area, destination_area, departure_time, max_packages: int = 5) -> SharedRoute:
    if max_packages < 1:
        raise DeliveryError("A route must allow at least 1 package.")
    return SharedRoute.objects.create(
        rider=rider, origin_area=origin_area, destination_area=destination_area,
        departure_time=departure_time, max_packages=max_packages,
    )


@transaction.atomic
def publish_route(rider, route_id: int) -> SharedRoute:
    try:
        route = SharedRoute.objects.select_for_update().get(pk=route_id, rider=rider)
    except SharedRoute.DoesNotExist as exc:
        raise DeliveryError("Route not found.") from exc
    if route.status != SharedRoute.Status.DRAFT:
        raise DeliveryError("Only a draft route can be published.")
    route.status = SharedRoute.Status.PUBLISHED
    route.save(update_fields=["status"])
    return route


@transaction.atomic
def attach_job_to_route(rider, route_id: int, job_id: int) -> DeliveryJob:
    """Combines 'accept this job' with 'group it into this route' in one
    step, mirroring how a plain accept_job works for a normal delivery —
    a rider doesn't separately accept then attach."""
    try:
        route = SharedRoute.objects.select_for_update().get(pk=route_id, rider=rider)
    except SharedRoute.DoesNotExist as exc:
        raise DeliveryError("Route not found.") from exc

    if route.status not in SharedRoute.OPEN_FOR_ATTACHMENT:
        raise DeliveryError("This route is not open for new packages.")
    if route.packages.filter(status__in=DeliveryJob.ACTIVE_STATUSES).count() >= route.max_packages:
        raise DeliveryError("This route is already at capacity.")

    try:
        job = DeliveryJob.objects.select_for_update().get(pk=job_id)
    except DeliveryJob.DoesNotExist as exc:
        raise DeliveryError("Delivery job not found.") from exc

    if job.status != DeliveryJob.Status.REQUESTED:
        raise DeliveryError("This job is no longer available.")
    if job.delivery_type != DeliveryJob.DeliveryType.SHARED_ROUTE:
        raise DeliveryError("Only shared-route deliveries can be attached to a route.")
    if job.dropoff_area_id != route.destination_area_id:
        raise DeliveryError("This job's dropoff area doesn't match the route's destination.")
    if job.pickup_merchant.area_id != route.origin_area_id:
        raise DeliveryError("This job's pickup area doesn't match the route's origin.")

    _transition(job, DeliveryJob.Status.ACCEPTED, actor=rider.user, rider=rider, route=route, assigned_at=timezone.now())
    return job


@transaction.atomic
def complete_route(rider, route_id: int) -> SharedRoute:
    try:
        route = SharedRoute.objects.select_for_update().get(pk=route_id, rider=rider)
    except SharedRoute.DoesNotExist as exc:
        raise DeliveryError("Route not found.") from exc

    if route.status not in (SharedRoute.Status.PUBLISHED, SharedRoute.Status.IN_PROGRESS):
        raise DeliveryError("Only a published or in-progress route can be completed.")

    still_active = route.packages.filter(status__in=DeliveryJob.ACTIVE_STATUSES).exists()
    if still_active:
        raise DeliveryError("This route still has packages in progress.")

    route.status = SharedRoute.Status.COMPLETED
    route.save(update_fields=["status"])
    return route


def cancel_route(rider, route_id: int) -> SharedRoute:
    try:
        route = SharedRoute.objects.get(pk=route_id, rider=rider)
    except SharedRoute.DoesNotExist as exc:
        raise DeliveryError("Route not found.") from exc
    if route.status in (SharedRoute.Status.COMPLETED, SharedRoute.Status.CANCELLED):
        raise DeliveryError("This route is already closed.")
    if route.packages.filter(status__in=DeliveryJob.ACTIVE_STATUSES).exists():
        raise DeliveryError("Cannot cancel a route with packages still in progress.")
    route.status = SharedRoute.Status.CANCELLED
    route.save(update_fields=["status"])
    return route
