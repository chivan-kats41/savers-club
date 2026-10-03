import uuid

from django.conf import settings
from django.db import models


class TimeStampedModel(models.Model):
    """Abstract base giving every model created_at/updated_at for free."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class UUIDModel(models.Model):
    """Abstract base for models that need a public, non-sequential ID."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class Area(TimeStampedModel):
    """A launch/service area (e.g. Mutungo, Kitintale). Backs geolocation
    and offer-radius logic across offers/deliveries/agents."""

    name = models.CharField(max_length=120, unique=True)
    is_launch_area = models.BooleanField(default=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class SystemSetting(TimeStampedModel):
    """Admin-configurable key/value business settings (subscription price,
    commission %, fees, limits, etc.) so nothing is hard-coded in views.

    `value` is always stored as text; typed helpers on the model /
    a settings-service layer (added in a later phase) handle casting.
    """

    key = models.CharField(max_length=100, unique=True)
    value = models.TextField()
    description = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["key"]

    def __str__(self):
        return f"{self.key} = {self.value}"


class AuditLog(TimeStampedModel):
    """Immutable audit trail. Written to, never edited or deleted from
    application code — see core/admin.py for read-only enforcement."""

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_logs",
    )
    action = models.CharField(max_length=100)
    object_type = models.CharField(max_length=100, blank=True)
    object_id = models.CharField(max_length=64, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    request_id = models.CharField(max_length=64, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["actor", "created_at"]),
            models.Index(fields=["action", "created_at"]),
            models.Index(fields=["object_type", "object_id"]),
        ]

    def __str__(self):
        return f"{self.action} by {self.actor_id} @ {self.created_at:%Y-%m-%d %H:%M}"


class RiskEvent(TimeStampedModel):
    """A lightweight fraud/risk signal — repeated failed payments, OTP
    lockouts, suspicious redemption attempts, rapid account creation from
    one IP, etc. Per spec section 33: these inform admin review, they
    never auto-block a user off a single signal."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="risk_events"
    )
    event_type = models.CharField(max_length=50)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    reviewed = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "event_type", "created_at"])]

    def __str__(self):
        return f"{self.event_type} - {self.user} @ {self.created_at:%Y-%m-%d %H:%M}"


class AdminCapability(models.Model):
    """No table rows are ever created for this model — it exists purely
    so its Meta.permissions become real, checkable auth.Permission rows
    (Django creates them automatically on migrate, but only for models
    Django actually loads — this must live in models.py, not a separate
    module, or the app registry never sees it and no permissions get
    created). Grant these via Django Groups/user_permissions in the
    admin, or through seed_admin_group for a sensible default set.
    SUPER_ADMIN bypasses all of these via is_superuser=True — see
    accounts.permissions.HasCapability.
    """

    class Meta:
        managed = False  # no database table
        default_permissions = ()  # suppress the default add/change/delete/view perms
        permissions = [
            ("payments_view", "Can view payments"),
            ("payments_refund", "Can refund payments"),
            ("payments_settle", "Can settle payments"),
            ("withdrawals_approve", "Can approve withdrawals"),
            ("withdrawals_reverse", "Can reverse withdrawals"),
            ("users_suspend", "Can suspend/reactivate user accounts"),
            ("merchant_verify", "Can verify merchants"),
            ("rider_verify", "Can verify riders"),
            ("agent_manage", "Can onboard/manage agents"),
            ("fees_manage", "Can manage platform fees"),
            ("settings_manage", "Can manage platform settings"),
            ("reports_view", "Can view admin reports"),
            ("offers_moderate", "Can approve/reject/pause offers"),
            ("notifications_broadcast", "Can send notifications to groups of users"),
            ("content_manage", "Can manage areas, categories, pickup points and agent tasks"),
        ]
