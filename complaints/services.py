from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Complaint, ComplaintMessage, ComplaintResolution


class ComplaintError(ValidationError):
    pass


def file_complaint(member, subject: str, description: str) -> Complaint:
    if not subject.strip() or not description.strip():
        raise ComplaintError("Subject and description are required.")
    return Complaint.objects.create(member=member, area=member.area, subject=subject, description=description)


@transaction.atomic
def resolve_complaint(actor_user, agent, complaint_id: int, resolution_note: str) -> Complaint:
    try:
        complaint = Complaint.objects.select_for_update().get(pk=complaint_id)
    except Complaint.DoesNotExist as exc:
        raise ComplaintError("Complaint not found.") from exc

    if agent is not None and not agent.covers_area(complaint.area_id):
        raise ComplaintError("This complaint is outside your assigned areas.")

    if complaint.status in (Complaint.Status.RESOLVED, Complaint.Status.REJECTED):
        raise ComplaintError("This complaint is already closed.")

    complaint.status = Complaint.Status.RESOLVED
    complaint.save(update_fields=["status"])
    ComplaintResolution.objects.create(complaint=complaint, resolved_by=actor_user, resolution_note=resolution_note)
    ComplaintMessage.objects.create(complaint=complaint, sender=actor_user, message=resolution_note)

    from notifications.services.dispatch import notify

    notify(
        complaint.member.user, "complaint", "Your complaint was resolved",
        f"'{complaint.subject}' has been resolved: {resolution_note}",
    )
    return complaint


@transaction.atomic
def escalate_complaint(agent, complaint_id: int, note: str) -> Complaint:
    try:
        complaint = Complaint.objects.select_for_update().get(pk=complaint_id)
    except Complaint.DoesNotExist as exc:
        raise ComplaintError("Complaint not found.") from exc

    if not agent.covers_area(complaint.area_id):
        raise ComplaintError("This complaint is outside your assigned areas.")
    if complaint.status in (Complaint.Status.RESOLVED, Complaint.Status.REJECTED):
        raise ComplaintError("This complaint is already closed.")

    complaint.status = Complaint.Status.ESCALATED
    complaint.assigned_agent = agent
    complaint.save(update_fields=["status", "assigned_agent"])
    if note:
        ComplaintMessage.objects.create(complaint=complaint, sender=agent.user, message=note)
    return complaint


@transaction.atomic
def start_investigating(agent, complaint_id: int) -> Complaint:
    try:
        complaint = Complaint.objects.select_for_update().get(pk=complaint_id)
    except Complaint.DoesNotExist as exc:
        raise ComplaintError("Complaint not found.") from exc

    if not agent.covers_area(complaint.area_id):
        raise ComplaintError("This complaint is outside your assigned areas.")
    if complaint.status != Complaint.Status.OPEN:
        raise ComplaintError("Only an open complaint can be picked up.")

    complaint.status = Complaint.Status.INVESTIGATING
    complaint.assigned_agent = agent
    complaint.save(update_fields=["status", "assigned_agent"])
    return complaint
