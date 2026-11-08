from django.conf import settings
from django.db import models

from core.models import Area, TimeStampedModel


class UserLocation(TimeStampedModel):
    """One row per user: their location preferences and last known position.

    Privacy by design: nothing about where a user *is* is stored unless they switch ``share_location`` on, and the
    trail in LocationHistory is a separate opt-in (``save_history``). Both default to OFF.
    """

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="location_state")
    share_location = models.BooleanField(default=False, help_text="Remember my last location to show deals near me.")
    save_history = models.BooleanField(default=False, help_text="Keep a trail of where I used the app (visible only to me).")
    # "I am in X right now" picked by hand, overrides the area chosen at registration.
    area_override = models.ForeignKey(Area, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    accuracy_m = models.PositiveIntegerField(null=True, blank=True)
    area = models.ForeignKey(Area, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    located_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Location settings for {self.user_id}"


class LocationHistory(TimeStampedModel):
    class Source(models.TextChoices):
        BROWSER = "browser", "Device location"
        MANUAL = "manual", "Chosen by hand"
        DROPOFF = "dropoff", "Delivery drop-off"
        RIDER_LIVE = "rider_live", "Rider live position (during a delivery)"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="location_history")
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    accuracy_m = models.PositiveIntegerField(null=True, blank=True)
    area = models.ForeignKey(Area, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    place_label = models.CharField(max_length=255, blank=True)
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.BROWSER)
    job = models.ForeignKey(
        "deliveries.DeliveryJob", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["source", "created_at"]),
            models.Index(fields=["job", "created_at"]),
        ]

    def __str__(self):
        return f"{self.user_id} @ {self.latitude},{self.longitude} ({self.source})"
