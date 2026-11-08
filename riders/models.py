from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import models

from core.uploads import private_storage

from core.models import Area, TimeStampedModel


def validate_document_size(file):
    max_bytes = 8 * 1024 * 1024
    if file.size > max_bytes:
        raise ValidationError("File must be 8MB or smaller.")


class Rider(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending verification"
        VERIFIED = "verified", "Verified"
        SUSPENDED = "suspended", "Suspended"
        REJECTED = "rejected", "Rejected"

    class VehicleType(models.TextChoices):
        BODA = "boda", "Boda boda"
        BICYCLE = "bicycle", "Bicycle"
        VAN = "van", "Van"
        OTHER = "other", "Other"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="rider_profile")
    area = models.ForeignKey(Area, on_delete=models.PROTECT, related_name="riders")

    vehicle_type = models.CharField(max_length=20, choices=VehicleType.choices, default=VehicleType.BODA)
    plate_number = models.CharField(max_length=30, blank=True)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="riders_verified"
    )
    verified_at = models.DateTimeField(null=True, blank=True)

    # Basic availability toggle. Live GPS tracking (RiderLocation) needs
    # real-time infra (Channels/WebSockets, spec section 73) — deferred.
    is_available = models.BooleanField(default=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["area", "status", "is_available"])]

    def __str__(self):
        return str(self.user)


class RiderVerification(TimeStampedModel):
    rider = models.ForeignKey(Rider, on_delete=models.CASCADE, related_name="verifications")
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="rider_verifications_done"
    )
    outcome = models.CharField(max_length=20, choices=Rider.Status.choices)
    checklist = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.rider} -> {self.outcome} ({self.created_at:%Y-%m-%d})"


class RiderDocument(TimeStampedModel):
    class DocType(models.TextChoices):
        ID_DOCUMENT = "id_document", "ID document"
        DRIVING_PERMIT = "driving_permit", "Driving permit"
        VEHICLE_PHOTO = "vehicle_photo", "Vehicle photo"
        OTHER = "other", "Other"

    rider = models.ForeignKey(Rider, on_delete=models.CASCADE, related_name="documents")
    doc_type = models.CharField(max_length=30, choices=DocType.choices)
    file = models.FileField(
        upload_to="rider_documents/%Y/%m/",
        storage=private_storage,
        validators=[FileExtensionValidator(["jpg", "jpeg", "png", "pdf"]), validate_document_size],
    )
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")

    class Meta:
        ordering = ["-created_at"]
