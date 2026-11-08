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
    # Browser/phone push. Only ever sent to devices that subscribed on purpose.
    push_enabled = models.BooleanField(default=True)
    # "A hot deal appeared near me" alerts: opt-in (default off), at most one a day, never by SMS.
    deal_alerts_enabled = models.BooleanField(default=False)

    def __str__(self):
        return f"Notification prefs for {self.user}"


class PushSubscription(TimeStampedModel):
    """One browser/device that agreed to receive Web Push for a user. ``endpoint`` is the push service URL
    (unique per device); p256dh/auth are the keys the payload is encrypted with. Removed automatically when the
    push service says the subscription is gone (HTTP 404/410)."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="push_subscriptions")
    endpoint = models.CharField(max_length=500, unique=True)
    p256dh = models.CharField(max_length=255)
    auth = models.CharField(max_length=255)
    user_agent = models.CharField(max_length=255, blank=True)
    last_success_at = models.DateTimeField(null=True, blank=True)
    failure_count = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user"])]

    def __str__(self):
        return f"Push device of {self.user_id}"
