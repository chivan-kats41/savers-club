from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import models
from django.utils import timezone

from core.models import Area, TimeStampedModel


def validate_image_size(file):
    max_bytes = 5 * 1024 * 1024
    if file.size > max_bytes:
        raise ValidationError("Image must be 5MB or smaller.")


class OfferCategory(TimeStampedModel):
    key = models.SlugField(max_length=50, unique=True)
    label = models.CharField(max_length=100)
    emoji = models.CharField(max_length=8, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "Offer categories"
        ordering = ["label"]

    def __str__(self):
        return self.label


class Offer(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending approval"
        ACTIVE = "active", "Active"
        PAUSED = "paused", "Paused"
        REJECTED = "rejected", "Rejected"
        REPORTED = "reported", "Reported"
        EXPIRED = "expired", "Expired"

    class PackagingStatus(models.TextChoices):
        UNSPECIFIED = "unspecified", "Not specified"
        SEALED = "sealed", "Sealed / factory packaging"
        REPACKAGED = "repackaged", "Repackaged by merchant"
        LOOSE = "loose", "Loose / unpackaged"

    merchant = models.ForeignKey("merchants.Merchant", on_delete=models.CASCADE, related_name="offers")
    category = models.ForeignKey(OfferCategory, on_delete=models.PROTECT, related_name="offers")
    area = models.ForeignKey(Area, on_delete=models.PROTECT, related_name="offers")

    item_name = models.CharField(max_length=150)
    normal_price = models.DecimalField(max_digits=12, decimal_places=2)
    member_price = models.DecimalField(max_digits=12, decimal_places=2)
    quantity = models.PositiveIntegerField(default=0)

    pickup_location = models.CharField(max_length=255, blank=True)
    delivery_available = models.BooleanField(default=False)
    offer_radius_km = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    packaging_status = models.CharField(
        max_length=20, choices=PackagingStatus.choices, default=PackagingStatus.UNSPECIFIED
    )

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    visibility_score = models.PositiveIntegerField(default=0)
    views_count = models.PositiveIntegerField(default=0)

    expires_at = models.DateTimeField()

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "expires_at"]),
            models.Index(fields=["area", "category", "status"]),
        ]

    def clean(self):
        errors = {}
        if self.member_price is not None and self.normal_price is not None:
            if self.member_price > self.normal_price:
                errors["member_price"] = "Member price cannot exceed the normal price."
        if self.quantity is not None and self.quantity < 0:
            errors["quantity"] = "Quantity cannot be negative."
        if self.expires_at and self.expires_at <= timezone.now():
            errors["expires_at"] = "Expiry must be in the future."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    @property
    def possible_saving(self) -> Decimal:
        return (self.normal_price or Decimal("0")) - (self.member_price or Decimal("0"))

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    def __str__(self):
        return f"{self.item_name} — {self.merchant}"


class OfferImage(TimeStampedModel):
    offer = models.ForeignKey(Offer, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(
        upload_to="offers/%Y/%m/",
        validators=[FileExtensionValidator(["jpg", "jpeg", "png", "webp"]), validate_image_size],
    )
    is_primary = models.BooleanField(default=False)

    class Meta:
        ordering = ["-is_primary", "created_at"]


class OfferInteraction(TimeStampedModel):
    """Real interaction tracking so merchant/admin stats (views, calls,
    WhatsApp clicks, delivery-request clicks) come from the database
    instead of a static counter — see spec section 64 (dashboard stats
    must all be DB-derived)."""

    class Kind(models.TextChoices):
        VIEW = "view", "View"
        CALL = "call", "Call"
        WHATSAPP = "whatsapp", "WhatsApp"
        DELIVERY_REQUEST_CLICK = "delivery_request_click", "Delivery request click"

    offer = models.ForeignKey(Offer, on_delete=models.CASCADE, related_name="interactions")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    kind = models.CharField(max_length=30, choices=Kind.choices)

    class Meta:
        indexes = [models.Index(fields=["offer", "kind", "created_at"])]
