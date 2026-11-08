import hashlib
import secrets
from datetime import timedelta

from django.conf import settings as dj_settings
from django.db import models
from django.utils import timezone

from core.models import Area, TimeStampedModel


class SharedRoute(TimeStampedModel):
    """A rider's declared trip (area A -> area B, at roughly a given
    time) that multiple shared_route DeliveryJobs can attach to — the
    grouping layer the spec calls SharedRoute/RoutePackage. Individual
    DeliveryJobs keep their own full state machine unchanged (see
    below); a route is a visibility/capacity construct on top, not a
    replacement for per-job tracking. Commission math is untouched —
    it's still computed per job from delivery_type, exactly as before
    this model existed.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        IN_PROGRESS = "in_progress", "In progress"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    OPEN_FOR_ATTACHMENT = {Status.PUBLISHED}

    rider = models.ForeignKey("riders.Rider", on_delete=models.CASCADE, related_name="shared_routes")
    origin_area = models.ForeignKey(Area, on_delete=models.PROTECT, related_name="+")
    destination_area = models.ForeignKey(Area, on_delete=models.PROTECT, related_name="+")
    departure_time = models.DateTimeField()
    max_packages = models.PositiveSmallIntegerField(default=5)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)

    class Meta:
        ordering = ["-departure_time"]
        indexes = [models.Index(fields=["status", "origin_area", "destination_area"])]

    def __str__(self):
        return f"{self.rider} {self.origin_area} -> {self.destination_area} @ {self.departure_time:%Y-%m-%d %H:%M}"


class DeliveryJob(TimeStampedModel):
    class Status(models.TextChoices):
        REQUESTED = "requested", "Requested"
        ASSIGNED = "assigned", "Assigned"  # reserved for a future admin-push dispatch flow
        ACCEPTED = "accepted", "Accepted"
        ARRIVED_AT_SELLER = "arrived_at_seller", "Arrived at seller"
        PICKED_UP = "picked_up", "Picked up"
        ON_ROUTE = "on_route", "On route"
        DELIVERED = "delivered", "Delivered"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    class DeliveryType(models.TextChoices):
        NORMAL = "normal", "Normal nearby delivery"  # local price, no platform commission
        SHARED_ROUTE = "shared_route", "Shared-route delivery"  # platform commission applies

    class PaymentMethod(models.TextChoices):
        ONLINE = "online", "Paid online by customer"
        CASH = "cash", "Cash on delivery"

    class PaymentStatus(models.TextChoices):
        UNPAID = "unpaid", "Awaiting online payment"          # online fare not paid yet: hidden from riders
        PAID = "paid", "Paid online"
        CASH_PENDING = "cash_pending", "Cash due on delivery"
        CASH_COLLECTED = "cash_collected", "Cash collected"
        REFUND_DUE = "refund_due", "Refund due to customer"   # paid online, then the delivery failed / was cancelled

    ACTIVE_STATUSES = [
        Status.REQUESTED, Status.ASSIGNED, Status.ACCEPTED,
        Status.ARRIVED_AT_SELLER, Status.PICKED_UP, Status.ON_ROUTE,
    ]

    claim = models.OneToOneField(
        "claims.OfferClaim", null=True, blank=True, on_delete=models.SET_NULL, related_name="delivery_job"
    )
    rider = models.ForeignKey(
        "riders.Rider", null=True, blank=True, on_delete=models.SET_NULL, related_name="delivery_jobs"
    )
    route = models.ForeignKey(
        SharedRoute, null=True, blank=True, on_delete=models.SET_NULL, related_name="packages"
    )
    pickup_merchant = models.ForeignKey("merchants.Merchant", on_delete=models.PROTECT, related_name="delivery_jobs")
    dropoff_area = models.ForeignKey(Area, on_delete=models.PROTECT, related_name="+")
    dropoff_address = models.CharField(max_length=255)
    # Where the drop-off really is (from the address search or a pin dropped on the map). Optional: a job without
    # coordinates still works exactly as before, riders just see the written address.
    dropoff_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    dropoff_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    dropoff_geocoded = models.BooleanField(default=False, help_text="True when the point came from an address search.")

    delivery_type = models.CharField(max_length=20, choices=DeliveryType.choices, default=DeliveryType.NORMAL)
    fare = models.DecimalField(max_digits=10, decimal_places=2)
    # How the delivery fare is settled. Defaults describe a prepaid job so rows created without a choice behave as before.
    payment_method = models.CharField(max_length=10, choices=PaymentMethod.choices, default=PaymentMethod.ONLINE)
    payment_status = models.CharField(max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PAID)
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.REQUESTED)

    assigned_at = models.DateTimeField(null=True, blank=True)
    picked_up_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)
    failure_reason = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "dropoff_area"]),
            models.Index(fields=["rider", "status"]),
        ]

    def __str__(self):
        return f"Delivery #{self.pk} ({self.status})"


class DeliveryStatusHistory(TimeStampedModel):
    job = models.ForeignKey(DeliveryJob, on_delete=models.CASCADE, related_name="status_history")
    from_status = models.CharField(max_length=30, blank=True)
    to_status = models.CharField(max_length=30)
    changed_by = models.ForeignKey(
        dj_settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-created_at"]


def _hash_code(raw_code: str) -> str:
    return hashlib.sha256(raw_code.encode()).hexdigest()


class DeliveryOTP(TimeStampedModel):
    """Customer hands the rider this code on delivery. Hashed at rest,
    same pattern as accounts.PhoneVerification — never store the raw
    code."""

    job = models.OneToOneField(DeliveryJob, on_delete=models.CASCADE, related_name="otp")
    code_hash = models.CharField(max_length=64)
    attempts = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=5)
    is_used = models.BooleanField(default=False)
    expires_at = models.DateTimeField()

    @classmethod
    def issue(cls, job, ttl_minutes=None):
        ttl_minutes = ttl_minutes or dj_settings.DELIVERY_OTP_EXPIRY_MINUTES
        raw_code = f"{secrets.randbelow(10_000):04d}"
        obj, _ = cls.objects.update_or_create(
            job=job,
            defaults={
                "code_hash": _hash_code(raw_code),
                "attempts": 0,
                "max_attempts": dj_settings.DELIVERY_OTP_MAX_ATTEMPTS,
                "is_used": False,
                "expires_at": timezone.now() + timedelta(minutes=ttl_minutes),
            },
        )
        return obj, raw_code

    def is_valid(self):
        return not self.is_used and self.attempts < self.max_attempts and timezone.now() < self.expires_at

    def verify_code(self, raw_code):
        if not self.is_valid():
            return False
        self.attempts += 1
        matched = secrets.compare_digest(self.code_hash, _hash_code(raw_code))
        if matched:
            self.is_used = True
        self.save(update_fields=["attempts", "is_used"])
        return matched


class RiderEarning(TimeStampedModel):
    """One row per completed delivery. Commission is calculated
    server-side from core.SystemSetting at delivery-completion time —
    never hard-coded, never trusted from the client."""

    rider = models.ForeignKey("riders.Rider", on_delete=models.PROTECT, related_name="earnings")
    delivery_job = models.OneToOneField(DeliveryJob, on_delete=models.PROTECT, related_name="earning")

    gross_amount = models.DecimalField(max_digits=10, decimal_places=2)
    commission_amount = models.DecimalField(max_digits=10, decimal_places=2)
    net_amount = models.DecimalField(max_digits=10, decimal_places=2)
    # Cash-on-delivery fare the rider already holds. It is deducted from the rider's withdrawable balance,
    # so the platform never pays out a fare the customer already handed over in cash.
    cash_collected = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.rider} earned {self.net_amount} (job #{self.delivery_job_id})"


class PickupPoint(TimeStampedModel):
    """A staffed collection/drop-off spot (shop, fuel station, agent kiosk) where
    parcels can be left for members instead of door delivery."""

    name = models.CharField(max_length=150)
    area = models.ForeignKey("core.Area", on_delete=models.PROTECT, related_name="pickup_points")
    address = models.CharField(max_length=255)
    contact_phone = models.CharField(max_length=20, blank=True)
    opening_hours = models.CharField(max_length=120, blank=True, help_text="e.g. Mon-Sat 8am-9pm")
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        dj_settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["area__name", "name"]

    def __str__(self):
        return f"{self.name} ({self.area})"
