from django.conf import settings
from django.db import models

from core.models import Area, TimeStampedModel


class Agent(TimeStampedModel):
    """Agents are onboarded directly by an admin (agent_manage capability)
    rather than through a public application/verification flow like
    merchants and riders — there's no AgentVerification model for that
    reason; if a public agent-application flow is needed later it can be
    added the same way merchants/riders work.
    """

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="agent_profile")
    areas = models.ManyToManyField(Area, related_name="agents", blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return str(self.user)

    def covers_area(self, area_id) -> bool:
        return self.areas.filter(pk=area_id).exists()


class AgentEarning(TimeStampedModel):
    """Credited when an agent completes a merchant/rider verification.
    Fee amounts are configurable via core.SystemSetting, never hard-coded."""

    class Source(models.TextChoices):
        MERCHANT_VERIFICATION = "merchant_verification", "Merchant verification"
        RIDER_VERIFICATION = "rider_verification", "Rider verification"

    agent = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name="earnings")
    source = models.CharField(max_length=30, choices=Source.choices)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    reference = models.CharField(max_length=100, blank=True, help_text="e.g. 'merchant:42' or 'rider:17'")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.agent} earned {self.amount} ({self.source})"


class PriceRecord(TimeStampedModel):
    """A price an agent physically observed in the field — feeds the
    price-comparison feature (spec section 62) with real, sourced data
    rather than merchant self-reported prices alone."""

    agent = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name="price_records")
    area = models.ForeignKey(Area, on_delete=models.PROTECT, related_name="+")
    category = models.ForeignKey("offers.OfferCategory", on_delete=models.PROTECT, related_name="+")
    item_name = models.CharField(max_length=150)
    price = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["area", "category", "created_at"])]

    def __str__(self):
        return f"{self.item_name} @ {self.price} ({self.area})"


class AgentTask(TimeStampedModel):
    class Kind(models.TextChoices):
        VERIFY_MERCHANT = "verify_merchant", "Verify a merchant"
        VERIFY_RIDER = "verify_rider", "Verify a rider"
        COLLECT_PRICES = "collect_prices", "Collect prices"
        FOLLOW_UP = "follow_up", "Follow up"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        DONE = "done", "Done"
        CANCELLED = "cancelled", "Cancelled"

    agent = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name="tasks")
    area = models.ForeignKey("core.Area", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    kind = models.CharField(max_length=30, choices=Kind.choices, default=Kind.OTHER)
    title = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    due_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["status", "due_at", "-created_at"]

    def __str__(self):
        return f"{self.title} → {self.agent}"
