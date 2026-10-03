import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone

from core.models import TimeStampedModel

# Excludes visually ambiguous characters (0/O, 1/I) since these codes get
# read aloud / typed by hand at a till.
CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"


def generate_claim_code() -> str:
    suffix = "".join(secrets.choice(CODE_ALPHABET) for _ in range(4))
    return f"1K-{suffix}"


class OfferClaim(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"  # reserved for a future approval workflow
        CLAIMED = "claimed", "Claimed"  # code issued, awaiting redemption
        REDEEMED = "redeemed", "Redeemed"
        EXPIRED = "expired", "Expired"
        CANCELLED = "cancelled", "Cancelled"
        REJECTED = "rejected", "Rejected"

    member = models.ForeignKey("members.Member", on_delete=models.CASCADE, related_name="claims")
    offer = models.ForeignKey("offers.Offer", on_delete=models.PROTECT, related_name="claims")

    code = models.CharField(max_length=16, unique=True, default=generate_claim_code)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.CLAIMED)

    # Snapshot at claim time — offer prices can change later, but the
    # member's expected saving must not move under them.
    expected_saving = models.DecimalField(max_digits=12, decimal_places=2)

    expires_at = models.DateTimeField()

    redeemed_at = models.DateTimeField(null=True, blank=True)
    redeemed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    redemption_attempts = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "expires_at"]),
            models.Index(fields=["member", "status"]),
        ]

    def __str__(self):
        return f"{self.code} — {self.offer.item_name} ({self.status})"

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at


class ClaimEvent(TimeStampedModel):
    claim = models.ForeignKey(OfferClaim, on_delete=models.CASCADE, related_name="events")
    event_type = models.CharField(max_length=50)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.claim} -> {self.event_type}"
