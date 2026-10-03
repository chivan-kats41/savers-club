from django.conf import settings
from django.db import models

from core.models import Area, TimeStampedModel


class Complaint(TimeStampedModel):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        INVESTIGATING = "investigating", "Investigating"
        RESOLVED = "resolved", "Resolved"
        ESCALATED = "escalated", "Escalated"
        REJECTED = "rejected", "Rejected"

    member = models.ForeignKey("members.Member", on_delete=models.CASCADE, related_name="complaints")
    area = models.ForeignKey(Area, on_delete=models.PROTECT, related_name="+")
    subject = models.CharField(max_length=200)
    description = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    assigned_agent = models.ForeignKey(
        "agents.Agent", null=True, blank=True, on_delete=models.SET_NULL, related_name="assigned_complaints"
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["area", "status"]), models.Index(fields=["assigned_agent", "status"])]

    def __str__(self):
        return f"{self.subject} ({self.status})"


class ComplaintMessage(TimeStampedModel):
    complaint = models.ForeignKey(Complaint, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    message = models.TextField()

    class Meta:
        ordering = ["created_at"]


class ComplaintResolution(TimeStampedModel):
    complaint = models.OneToOneField(Complaint, on_delete=models.CASCADE, related_name="resolution")
    resolved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    resolution_note = models.TextField()

    def __str__(self):
        return f"Resolution for {self.complaint}"
