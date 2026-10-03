from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import models

from core.models import Area, TimeStampedModel
from offers.models import OfferCategory


def validate_document_size(file):
    max_bytes = 8 * 1024 * 1024
    if file.size > max_bytes:
        raise ValidationError("File must be 8MB or smaller.")


class Merchant(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending verification"
        VERIFIED = "verified", "Verified"
        SUSPENDED = "suspended", "Suspended"
        REJECTED = "rejected", "Rejected"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="merchant_profile")
    business_name = models.CharField(max_length=150)
    category = models.ForeignKey(OfferCategory, on_delete=models.PROTECT, related_name="merchants")
    vendor_type = models.CharField(max_length=100, blank=True)

    area = models.ForeignKey(Area, on_delete=models.PROTECT, related_name="merchants")
    address = models.CharField(max_length=255, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    phone = models.CharField(max_length=20, blank=True)
    whatsapp = models.CharField(max_length=20, blank=True)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="merchants_verified",
    )
    verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["business_name"]
        indexes = [models.Index(fields=["area", "status"])]

    def __str__(self):
        return self.business_name


class MerchantVerification(TimeStampedModel):
    """Append-only evidence record for each verification pass. Merchant.status
    reflects the current outcome; this table is the audit trail behind it —
    per spec, verification must never be a bare `verified=True` flag."""

    merchant = models.ForeignKey(Merchant, on_delete=models.CASCADE, related_name="verifications")
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="merchant_verifications_done"
    )
    outcome = models.CharField(max_length=20, choices=Merchant.Status.choices)
    checklist = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "e.g. {real_person_met: true, phone_confirmed: true, "
            "location_confirmed: true, stock_photo_taken: true, "
            "current_prices_checked: true, packaging_hygiene_ok: true, "
            "duplicate_account_check_passed: true}"
        ),
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.merchant} -> {self.outcome} ({self.created_at:%Y-%m-%d})"


class MerchantDocument(TimeStampedModel):
    class DocType(models.TextChoices):
        ID_DOCUMENT = "id_document", "ID document"
        BUSINESS_PERMIT = "business_permit", "Business permit"
        STOCK_PHOTO = "stock_photo", "Stock photo"
        STOREFRONT_PHOTO = "storefront_photo", "Storefront photo"
        OTHER = "other", "Other"

    merchant = models.ForeignKey(Merchant, on_delete=models.CASCADE, related_name="documents")
    doc_type = models.CharField(max_length=30, choices=DocType.choices)
    file = models.FileField(
        upload_to="merchant_documents/%Y/%m/",
        validators=[
            FileExtensionValidator(["jpg", "jpeg", "png", "pdf"]),
            validate_document_size,
        ],
    )
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")

    class Meta:
        ordering = ["-created_at"]
