from django.core.exceptions import ValidationError
from django.db import models

from core.models import TimeStampedModel


class PromotionPackage(TimeStampedModel):
    """Admin-configurable — nothing about price/duration/boost is
    hard-coded. A merchant buys one of these to boost a specific
    offer's visibility_score for a fixed period."""

    code = models.SlugField(max_length=30, unique=True)
    label = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    duration_days = models.PositiveIntegerField()
    visibility_boost = models.PositiveIntegerField(help_text="Added to the offer's visibility_score while active.")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["price"]

    def __str__(self):
        return f"{self.label} (UGX {self.price:,.0f} / {self.duration_days}d, +{self.visibility_boost})"


class PromotionPurchase(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending payment"
        ACTIVE = "active", "Active"
        EXPIRED = "expired", "Expired"
        FAILED = "failed", "Failed"

    merchant = models.ForeignKey("merchants.Merchant", on_delete=models.CASCADE, related_name="promotion_purchases")
    offer = models.ForeignKey("offers.Offer", on_delete=models.CASCADE, related_name="promotion_purchases")
    package = models.ForeignKey(PromotionPackage, on_delete=models.PROTECT, related_name="purchases")

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    starts_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "expires_at"])]

    def clean(self):
        if self.offer_id and self.merchant_id and hasattr(self, "offer") and self.offer.merchant_id != self.merchant_id:
            raise ValidationError("A merchant can only promote their own offers.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.package} for {self.offer} ({self.status})"
