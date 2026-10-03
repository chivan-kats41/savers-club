from django.core.exceptions import ValidationError
from django.db import models

from core.models import Area, TimeStampedModel


class MemberRequest(TimeStampedModel):
    """A member asking for an item they haven't found on the platform —
    merchants browse open requests in their area and respond with
    availability/pricing, rather than the member searching existing
    offers (spec's ITEM REQUESTS feature)."""

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        RESPONDED = "responded", "Has responses"
        FULFILLED = "fulfilled", "Fulfilled"
        CANCELLED = "cancelled", "Cancelled"
        EXPIRED = "expired", "Expired"

    member = models.ForeignKey("members.Member", on_delete=models.CASCADE, related_name="item_requests")
    area = models.ForeignKey(Area, on_delete=models.PROTECT, related_name="+")
    item_name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    max_budget = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    fulfilled_response = models.ForeignKey(
        "RequestResponse", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["area", "status"]), models.Index(fields=["member", "status"])]

    def clean(self):
        if self.max_budget is not None and self.max_budget <= 0:
            raise ValidationError({"max_budget": "Budget must be positive if given."})

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.item_name} ({self.status})"


class RequestResponse(TimeStampedModel):
    request = models.ForeignKey(MemberRequest, on_delete=models.CASCADE, related_name="responses")
    merchant = models.ForeignKey("merchants.Merchant", on_delete=models.CASCADE, related_name="request_responses")
    message = models.TextField(blank=True)
    price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = ("request", "merchant")

    def clean(self):
        if self.price is not None and self.price <= 0:
            raise ValidationError({"price": "Price must be positive if given."})

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.merchant} responded to {self.request}"
