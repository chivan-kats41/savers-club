from django.core.exceptions import ValidationError

from merchants.models import Merchant

from .models import Offer


class OfferError(ValidationError):
    pass


def create_offer(merchant: Merchant, **fields) -> Offer:
    if merchant.status != Merchant.Status.VERIFIED:
        raise OfferError("Only verified merchants can post offers.")

    offer = Offer(merchant=merchant, status=Offer.Status.PENDING, **fields)
    try:
        offer.save()
    except ValidationError as exc:
        raise OfferError("; ".join(exc.messages) if hasattr(exc, "messages") else str(exc))
    return offer


def update_offer(merchant: Merchant, offer_id: int, **fields) -> Offer:
    try:
        offer = Offer.objects.get(pk=offer_id, merchant=merchant)
    except Offer.DoesNotExist as exc:
        raise OfferError("Offer not found.") from exc

    for field, value in fields.items():
        setattr(offer, field, value)
    # Editing an already-approved offer sends it back for re-approval —
    # never let a merchant silently change price/quantity on a live offer
    # without another look.
    if offer.status == Offer.Status.ACTIVE:
        offer.status = Offer.Status.PENDING

    try:
        offer.save()
    except ValidationError as exc:
        raise OfferError("; ".join(exc.messages) if hasattr(exc, "messages") else str(exc))
    return offer


def delete_offer(merchant: Merchant, offer_id: int) -> None:
    try:
        offer = Offer.objects.get(pk=offer_id, merchant=merchant)
    except Offer.DoesNotExist as exc:
        raise OfferError("Offer not found.") from exc
    if offer.claims.exists():
        raise OfferError("This offer has existing claims and cannot be deleted — pause it instead.")
    offer.delete()


def pause_offer(merchant: Merchant, offer_id: int) -> Offer:
    try:
        offer = Offer.objects.get(pk=offer_id, merchant=merchant)
    except Offer.DoesNotExist as exc:
        raise OfferError("Offer not found.") from exc
    if offer.status != Offer.Status.ACTIVE:
        raise OfferError("Only an active offer can be paused.")
    offer.status = Offer.Status.PAUSED
    offer.save(update_fields=["status"])
    return offer
