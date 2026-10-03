from django.conf import settings
from django.db import models

from core.models import TimeStampedModel


class NotificationCategory(models.TextChoices):
    REGISTRATION = "registration", "Registration"
    SUBSCRIPTION_PAYMENT = "subscription_payment", "Subscription payment"
    CLAIM = "claim", "Claim"
    DELIVERY = "delivery", "Delivery"
    WITHDRAWAL = "withdrawal", "Withdrawal"
    COMPLAINT = "complaint", "Complaint"
    SECURITY = "security", "Security"
    OFFER = "offer", "Offer"
    ANNOUNCEMENT = "announcement", "Announcement"


class Notification(TimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    category = models.CharField(max_length=30, choices=NotificationCategory.choices)
    title = models.CharField(max_length=150)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "is_read", "created_at"])]

    def __str__(self):
        return f"{self.title} -> {self.user}"


class NotificationPreference(TimeStampedModel):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notification_preference")
    sms_enabled = models.BooleanField(default=True)
    email_enabled = models.BooleanField(default=True)
    in_app_enabled = models.BooleanField(default=True)

    def __str__(self):
        return f"Notification prefs for {self.user}"
