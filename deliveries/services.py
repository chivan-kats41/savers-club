import logging
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from core.services import route_commission_percent
from riders.models import Rider

from .models import DeliveryJob, DeliveryOTP, DeliveryStatusHistory, RiderEarning, SharedRoute

logger = logging.getLogger("deliveries")


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
def request_delivery(
    claim, merchant, dropoff_area, dropoff_address: str, delivery_type: str, fare: Decimal,
    payment_method: str = DeliveryJob.PaymentMethod.CASH,
    dropoff_latitude=None, dropoff_longitude=None, dropoff_geocoded: bool = False,
) -> DeliveryJob:
    """Open a delivery for a claim. The customer chooses how the fare is settled:

    * cash   -> visible to riders immediately; the rider collects the fare at the door (cash on delivery)
    * online -> created UNPAID and hidden from riders until the customer's mobile-money / card payment
                succeeds (see mark_fare_paid); abandoned unpaid jobs are cancelled by expire_unpaid_deliveries.
    """
    if payment_method not in DeliveryJob.PaymentMethod.values:
        raise DeliveryError("Choose how you will pay: online or cash on delivery.")
    existing = getattr(claim, "delivery_job", None) if claim is not None else None
    if existing is not None:
        raise DeliveryError("A delivery has already been requested for this claim.")
    if fare is None or fare <= 0:
        raise DeliveryError("Delivery fare must be positive.")

    online = payment_method == DeliveryJob.PaymentMethod.ONLINE
    job = DeliveryJob.objects.create(
        claim=claim,
        pickup_merchant=merchant,
        dropoff_area=dropoff_area,
        dropoff_address=dropoff_address,
        dropoff_latitude=dropoff_latitude,
        dropoff_longitude=dropoff_longitude,
        dropoff_geocoded=dropoff_geocoded,
        delivery_type=delivery_type,
        fare=fare,
        payment_method=payment_method,
        payment_status=DeliveryJob.PaymentStatus.UNPAID if online else DeliveryJob.PaymentStatus.CASH_PENDING,
        status=DeliveryJob.Status.REQUESTED,
    )
    DeliveryStatusHistory.objects.create(job=job, from_status="", to_status=job.status)
    return job


# Jobs riders may see and accept: not an online job still waiting for the customer's payment.
def open_jobs_for_riders():
    return DeliveryJob.objects.filter(status=DeliveryJob.Status.REQUESTED).exclude(
        payment_status=DeliveryJob.PaymentStatus.UNPAID
    )


@transaction.atomic
def mark_fare_paid(job: DeliveryJob) -> DeliveryJob:
    """Called only from a verified payment-provider confirmation. Releases the job to riders."""
    job = DeliveryJob.objects.select_for_update().get(pk=job.pk)
    if job.payment_status == DeliveryJob.PaymentStatus.PAID:
        return job  # idempotent: provider callbacks can repeat
    if job.status == DeliveryJob.Status.CANCELLED:
        # The customer paid just after we gave up on the job: the money is real, so flag it for refund.
        job.payment_status = DeliveryJob.PaymentStatus.REFUND_DUE
        job.save(update_fields=["payment_status"])
        logger.warning("Fare paid for cancelled delivery job=%s: marked refund_due", job.pk)
        return job
    job.payment_status = DeliveryJob.PaymentStatus.PAID
    job.save(update_fields=["payment_status"])
    return job


@transaction.atomic
def cancel_delivery(job: DeliveryJob, reason: str = "") -> DeliveryJob:
    """Cancel a job nobody has accepted yet. Frees the claim so the customer can request again."""
    job = DeliveryJob.objects.select_for_update().get(pk=job.pk)
    if job.status != DeliveryJob.Status.REQUESTED:
        raise DeliveryError("Only a delivery nobody has accepted yet can be cancelled.")
    refund = job.payment_status == DeliveryJob.PaymentStatus.PAID
    _transition(job, DeliveryJob.Status.CANCELLED, notes=reason or "cancelled", claim=None)
    if refund:
        job.payment_status = DeliveryJob.PaymentStatus.REFUND_DUE
        job.save(update_fields=["payment_status"])
    return job


UNPAID_JOB_MINUTES = 30


def expire_unpaid_deliveries(minutes: int = UNPAID_JOB_MINUTES) -> int:
    """Cancel online-pay jobs whose customer never completed payment, freeing the claim for a fresh request.
    A job with a payment still in flight with ioTec is left alone until that settles."""
    from payments.models import Payment

    cutoff = timezone.now() - timedelta(minutes=minutes)
    count = 0
    for job in DeliveryJob.objects.filter(
        status=DeliveryJob.Status.REQUESTED, payment_status=DeliveryJob.PaymentStatus.UNPAID, created_at__lt=cutoff
    ):
        if job.fare_payments.filter(status__in=(Payment.Status.CREATED, Payment.Status.PENDING, Payment.Status.SENT_TO_VENDOR)).exists():
            continue
        try:
            cancel_delivery(job, reason="payment not completed")
            count += 1
        except DeliveryError:
            pass
    return count


@transaction.atomic
def accept_job(rider: Rider, job_id: int) -> DeliveryJob:
    if rider.status != Rider.Status.VERIFIED:
        raise DeliveryError("Only verified riders can accept delivery jobs.")

    try:
        job = DeliveryJob.objects.select_for_update().get(pk=job_id)
    except DeliveryJob.DoesNotExist as exc:
        raise DeliveryError("Delivery job not found.") from exc

    if job.status != DeliveryJob.Status.REQUESTED or job.payment_status == DeliveryJob.PaymentStatus.UNPAID:
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


def _send_delivery_code(job: DeliveryJob, raw_otp: str) -> None:
    """Text the one-time code to the CUSTOMER (never to the rider). The rider must collect it at the door,
    which is what proves the parcel reached the right person."""
    if not job.claim_id:
        return
    from notifications.services.sms_gateway import send_sms

    phone = job.claim.member.user.phone
    text = (
        f"1K Saver Club: your delivery code is {raw_otp}. Give it to the rider only when you have received "
        f"your order from {job.pickup_merchant.business_name}. Never share it earlier."
    )
    if not send_sms(phone, text):
        logger.warning("Delivery code SMS could not be sent for job=%s; falling back to an in-app message", job.pk)
        # The SMS provider is down or not configured. Without this the customer would never receive the code and the
        # delivery could not be confirmed. The code is shown only inside the customer's own signed-in account (in-app
        # only: never pushed to a lock screen) and ONLY in this failure case, so working deployments never store it.
        from notifications.services.dispatch import notify

        notify(
            job.claim.member.user, "delivery", "Your delivery code",
            f"We couldn't text your delivery code, so it is here: {raw_otp}. Give it to the rider only when you have "
            f"received your order from {job.pickup_merchant.business_name}.",
            metadata={"job_id": job.pk, "url": "/member/#delivery", "_channels": ["in_app"]},
        )


def mark_picked_up(rider: Rider, job_id: int) -> tuple[DeliveryJob, str]:
    with transaction.atomic():
        job = _owned_active_job(rider, job_id, DeliveryJob.Status.ARRIVED_AT_SELLER)
        _transition(job, DeliveryJob.Status.PICKED_UP, actor=rider.user, picked_up_at=timezone.now())
        _, raw_otp = DeliveryOTP.issue(job)
    # After commit, so a rolled-back pickup never texts a code that does not exist.
    _send_delivery_code(job, raw_otp)
    return job, raw_otp


@transaction.atomic
def mark_on_route(rider: Rider, job_id: int) -> DeliveryJob:
    job = _owned_active_job(rider, job_id, DeliveryJob.Status.PICKED_UP)
    _transition(job, DeliveryJob.Status.ON_ROUTE, actor=rider.user)
    return job


def confirm_delivery(rider: Rider, job_id: int, otp_code: str) -> DeliveryJob:
    """NOTE: the failure is raised only AFTER the atomic block has committed. Raising inside it would roll
    back the attempt counter, so wrong guesses would never be counted and the code could be brute-forced."""
    with transaction.atomic():
        job = _owned_active_job(rider, job_id, DeliveryJob.Status.ON_ROUTE)

        try:
            otp = DeliveryOTP.objects.select_for_update().get(job=job)
        except DeliveryOTP.DoesNotExist as exc:
            raise DeliveryError("No delivery code was issued for this job.") from exc

        matched = otp.verify_code(otp_code)  # persists the attempt count
        if matched:
            _transition(job, DeliveryJob.Status.DELIVERED, actor=rider.user, delivered_at=timezone.now())

            gross = job.fare
            commission_pct = (
                route_commission_percent() if job.delivery_type == DeliveryJob.DeliveryType.SHARED_ROUTE else Decimal("0")
            )
            commission = (gross * commission_pct / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            net = gross - commission

            # Cash on delivery: the customer handed the fare to the rider, so it is already in the rider's pocket.
            # It is recorded against the rider's balance so the platform never pays the same fare out again.
            cash = Decimal("0")
            if job.payment_method == DeliveryJob.PaymentMethod.CASH:
                cash = gross
                job.payment_status = DeliveryJob.PaymentStatus.CASH_COLLECTED
                job.save(update_fields=["payment_status"])

            RiderEarning.objects.create(
                rider=rider, delivery_job=job, gross_amount=gross, commission_amount=commission, net_amount=net,
                cash_collected=cash,
            )

    if not matched:
        raise DeliveryError("Invalid or expired delivery code.")

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
    if job.payment_status == DeliveryJob.PaymentStatus.PAID:
        # The customer already paid online for a delivery that did not happen: owed back.
        job.payment_status = DeliveryJob.PaymentStatus.REFUND_DUE
        job.save(update_fields=["payment_status"])

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
