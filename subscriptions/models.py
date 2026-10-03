import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from core.models import TimeStampedModel


class SubscriptionPlan(TimeStampedModel):
    """Admin-configurable — nothing about price/period is hard-coded in
    application code. Default plan is UGX 1,000/month, but admins can
    add/edit plans (quarterly, yearly promo, etc.) without a deploy."""

    code = models.SlugField(max_length=30, unique=True)
    label = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    period_days = models.PositiveIntegerField(help_text="Billing period length, in days.")
    is_active = models.BooleanField(default=True)
    is_popular = models.BooleanField(default=False)
    benefits = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["price"]

    def __str__(self):
        return f"{self.label} (UGX {self.price:,.0f} / {self.period_days}d)"


class Subscription(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending first payment"
        ACTIVE = "active", "Active"
        PAUSED = "paused", "Paused"
        EXPIRED = "expired", "Expired"
        CANCELLED = "cancelled", "Cancelled"

    member = models.ForeignKey("members.Member", on_delete=models.CASCADE, related_name="subscriptions")
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.PROTECT, related_name="subscriptions")

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    current_period_start = models.DateTimeField(null=True, blank=True)
    current_period_end = models.DateTimeField(null=True, blank=True)
    auto_renew = models.BooleanField(default=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["member", "status"])]

    def __str__(self):
        return f"{self.member} — {self.plan.code} ({self.status})"

    @property
    def is_currently_active(self) -> bool:
        return (
            self.status == self.Status.ACTIVE
            and self.current_period_end is not None
            and self.current_period_end > timezone.now()
        )


class SubscriptionPayment(TimeStampedModel):
    """Placeholder payment record for a subscription charge. The real
    ioTec integration (OAuth client, collection request, callback
    handling) is built in the payments app in Phase 7 — this model exists
    now so Subscription.renew() has somewhere authoritative to record
    'a payment was requested' without faking success. Status only ever
    moves PENDING -> SUCCESS/FAILED via a real confirmation path; nothing
    in this app auto-activates a subscription from a frontend claim.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"

    subscription = models.ForeignKey(Subscription, on_delete=models.CASCADE, related_name="payments")
    external_reference = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)

    # Populated once the payments app (Phase 7) exists and wires a real
    # provider call to this record.
    provider = models.CharField(max_length=30, blank=True)
    provider_transaction_id = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def clean(self):
        if self.amount is not None and self.amount <= 0:
            raise ValidationError({"amount": "Amount must be positive."})

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)


class SubscriptionEvent(TimeStampedModel):
    subscription = models.ForeignKey(Subscription, on_delete=models.CASCADE, related_name="events")
    event_type = models.CharField(max_length=50)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.subscription} -> {self.event_type}"
