from core.models import TimeStampedModel
from django.db import models


class SavingsRecord(TimeStampedModel):
    """One row per successfully redeemed claim. This — not a running
    balance field anywhere — is the source of truth for a member's
    confirmed savings; dashboard totals are always computed by
    aggregating these rows, never stored/incremented directly (see
    savings/selectors.py).
    """

    claim = models.OneToOneField("claims.OfferClaim", on_delete=models.PROTECT, related_name="savings_record")
    member = models.ForeignKey("members.Member", on_delete=models.CASCADE, related_name="savings_records")
    merchant = models.ForeignKey("merchants.Merchant", on_delete=models.PROTECT, related_name="savings_records")

    normal_price = models.DecimalField(max_digits=12, decimal_places=2)
    member_price = models.DecimalField(max_digits=12, decimal_places=2)
    saving_amount = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["member", "created_at"])]

    def __str__(self):
        return f"{self.member} saved {self.saving_amount} via {self.claim.code}"
