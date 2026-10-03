from django.core.exceptions import ValidationError
from django.db import transaction

from merchants.models import Merchant

from .models import MemberRequest, RequestResponse


class ItemRequestError(ValidationError):
    pass


def file_request(member, item_name: str, description: str = "", max_budget=None) -> MemberRequest:
    if not item_name.strip():
        raise ItemRequestError("Item name is required.")
    req = MemberRequest(member=member, area=member.area, item_name=item_name, description=description, max_budget=max_budget)
    try:
        req.save()
    except ValidationError as exc:
        raise ItemRequestError("; ".join(exc.messages) if hasattr(exc, "messages") else str(exc))
    return req


@transaction.atomic
def respond_to_request(merchant: Merchant, request_id: int, message: str = "", price=None) -> RequestResponse:
    try:
        req = MemberRequest.objects.select_for_update().get(pk=request_id)
    except MemberRequest.DoesNotExist as exc:
        raise ItemRequestError("Request not found.") from exc

    if merchant.status != Merchant.Status.VERIFIED:
        raise ItemRequestError("Only verified merchants can respond to requests.")
    if req.status not in (MemberRequest.Status.OPEN, MemberRequest.Status.RESPONDED):
        raise ItemRequestError("This request is no longer open for responses.")
    if RequestResponse.objects.filter(request=req, merchant=merchant).exists():
        raise ItemRequestError("You have already responded to this request.")

    try:
        response = RequestResponse.objects.create(request=req, merchant=merchant, message=message, price=price)
    except ValidationError as exc:
        raise ItemRequestError("; ".join(exc.messages) if hasattr(exc, "messages") else str(exc))

    if req.status == MemberRequest.Status.OPEN:
        req.status = MemberRequest.Status.RESPONDED
        req.save(update_fields=["status"])

    from notifications.services.dispatch import notify

    notify(
        req.member.user, "offer", "New response to your request",
        f"{merchant.business_name} responded to your request for {req.item_name}.",
    )
    return response


@transaction.atomic
def fulfill_request(member, request_id: int, response_id: int | None = None) -> MemberRequest:
    try:
        req = MemberRequest.objects.select_for_update().get(pk=request_id, member=member)
    except MemberRequest.DoesNotExist as exc:
        raise ItemRequestError("Request not found.") from exc

    if req.status not in (MemberRequest.Status.OPEN, MemberRequest.Status.RESPONDED):
        raise ItemRequestError("This request cannot be marked fulfilled from its current state.")

    chosen = None
    if response_id is not None:
        chosen = RequestResponse.objects.filter(pk=response_id, request=req).first()
        if chosen is None:
            raise ItemRequestError("That response does not belong to this request.")

    req.status = MemberRequest.Status.FULFILLED
    req.fulfilled_response = chosen
    req.save(update_fields=["status", "fulfilled_response"])
    return req


def cancel_request(member, request_id: int) -> MemberRequest:
    try:
        req = MemberRequest.objects.get(pk=request_id, member=member)
    except MemberRequest.DoesNotExist as exc:
        raise ItemRequestError("Request not found.") from exc
    if req.status not in (MemberRequest.Status.OPEN, MemberRequest.Status.RESPONDED):
        raise ItemRequestError("This request cannot be cancelled from its current state.")
    req.status = MemberRequest.Status.CANCELLED
    req.save(update_fields=["status"])
    return req
