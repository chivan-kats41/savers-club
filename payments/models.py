import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from core.models import TimeStampedModel


class Payment(TimeStampedModel):
    """The provider-facing record for a single ioTec Pay collection
    attempt. `internal_reference` is what we send as ioTec's `externalId`
    — generated here, never accepted from the frontend. This is
    deliberately generic (`purpose` + a nullable link to whatever it's
    for) so card/mobile-money collection logic doesn't need to be
    duplicated per feature; subscriptions is the only purpose wired up
    so far, per spec section 10's unified /payments/initiate/ shape.
    """

    class Purpose(models.TextChoices):
        SUBSCRIPTION = "subscription", "Subscription"
        PROMOTION = "promotion", "Offer promotion"

    class Method(models.TextChoices):
        MOBILE_MONEY = "mobile_money", "Mobile money"
        CARD = "card", "Card"

    class Status(models.TextChoices):
        CREATED = "created", "Created"
        PENDING = "pending", "Pending"
        SENT_TO_VENDOR = "sent_to_vendor", "Sent to vendor"
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"
        EXPIRED = "expired", "Expired"
        REQUIRES_REVIEW = "requires_review", "Requires review"
        REFUNDED = "refunded", "Refunded"

    # Terminal states a callback must never move a payment out of.
    TERMINAL_STATUSES = {Status.SUCCESS, Status.FAILED, Status.CANCELLED, Status.REFUNDED}

    purpose = models.CharField(max_length=30, choices=Purpose.choices)
    subscription_payment = models.OneToOneField(
        "subscriptions.SubscriptionPayment", null=True, blank=True, on_delete=models.PROTECT, related_name="provider_payment"
    )
    promotion_purchase = models.OneToOneField(
        "promotions.PromotionPurchase", null=True, blank=True, on_delete=models.PROTECT, related_name="provider_payment"
    )

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="payments")
    method = models.CharField(max_length=20, choices=Method.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="UGX")

    internal_reference = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    provider = models.CharField(max_length=30, default="iotec")
    provider_transaction_id = models.CharField(max_length=100, blank=True)

    payer_phone = models.CharField(max_length=20, blank=True)
    payer_email = models.EmailField(blank=True)
    redirect_url = models.URLField(blank=True)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.CREATED)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["user", "status"]),
        ]

    def clean(self):
        if self.amount is not None and self.amount <= 0:
            raise ValidationError({"amount": "Amount must be positive."})

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.internal_reference} — {self.amount} {self.currency} ({self.status})"


class PaymentCallback(TimeStampedModel):
    """Immutable log of every callback ioTec sends us, processed or not —
    kept even for duplicates/invalid ones, since this table is the audit
    trail for 'what did the provider actually tell us and when'."""

    payment = models.ForeignKey(Payment, null=True, blank=True, on_delete=models.SET_NULL, related_name="callbacks")
    raw_payload = models.JSONField()
    provider_status = models.CharField(max_length=50, blank=True)
    provider_transaction_id = models.CharField(max_length=100, blank=True)
    processed = models.BooleanField(default=False)
    processing_notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["payment", "provider_status", "provider_transaction_id"])]


class Withdrawal(TimeStampedModel):
    """A disbursement request — rider (for now) cashing out earnings to
    mobile money. Funds are only ever considered available (see
    services/withdrawals.py) once counted against PENDING/PROCESSING/
    COMPLETED withdrawals, so the same earnings can't be withdrawn twice
    while a request is in flight.
    """

    class Source(models.TextChoices):
        RIDER_EARNINGS = "rider_earnings", "Rider earnings"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Sent to vendor"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        REVERSED = "reversed", "Reversed"

    TERMINAL_STATUSES = {Status.COMPLETED, Status.FAILED, Status.REVERSED}

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="withdrawals")
    source = models.CharField(max_length=30, choices=Source.choices)

    amount = models.DecimalField(max_digits=12, decimal_places=2)
    fee = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    net_amount = models.DecimalField(max_digits=12, decimal_places=2)
    phone = models.CharField(max_length=20)

    internal_reference = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    provider = models.CharField(max_length=30, default="iotec")
    provider_transaction_id = models.CharField(max_length=100, blank=True)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["status", "created_at"]),
        ]

    def clean(self):
        if self.amount is not None and self.amount <= 0:
            raise ValidationError({"amount": "Amount must be positive."})
        if self.net_amount is not None and self.net_amount <= 0:
            raise ValidationError({"net_amount": "Net amount after fees must be positive."})

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.internal_reference} — {self.net_amount} to {self.phone} ({self.status})"


class WithdrawalCallback(TimeStampedModel):
    withdrawal = models.ForeignKey(Withdrawal, null=True, blank=True, on_delete=models.SET_NULL, related_name="callbacks")
    raw_payload = models.JSONField()
    provider_status = models.CharField(max_length=50, blank=True)
    provider_transaction_id = models.CharField(max_length=100, blank=True)
    processed = models.BooleanField(default=False)
    processing_notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-created_at"]


class LedgerEntry(TimeStampedModel):
    """Every confirmed financial movement gets one immutable row here —
    never just `balance += amount`. This is a single-entry record per
    payment for now (suffices to prove 'money moved, here's proof');
    a full double-entry chart of accounts (platform revenue, rider
    payables, settlement batches) is its own later phase once
    disbursements/settlements exist to reconcile against.
    """

    class Direction(models.TextChoices):
        CREDIT = "credit", "Credit (platform received)"
        DEBIT = "debit", "Debit (platform paid out)"

    payment = models.ForeignKey(Payment, null=True, blank=True, on_delete=models.PROTECT, related_name="ledger_entries")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="ledger_entries")
    direction = models.CharField(max_length=10, choices=Direction.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    fee = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    net_amount = models.DecimalField(max_digits=12, decimal_places=2)
    reference = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "created_at"])]

    def __str__(self):
        return f"{self.direction} {self.net_amount} for {self.user}"
