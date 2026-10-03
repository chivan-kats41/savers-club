from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from merchants.models import Merchant
from offers.models import Offer

from .models import PromotionPackage, PromotionPurchase


class PromotionError(ValidationError):
    pass


@transaction.atomic
def create_pending_purchase(merchant: Merchant, offer_id: int, package: PromotionPackage) -> PromotionPurchase:
    """Opens a PENDING PromotionPurchase — mirrors subscriptions.services.
    initiate_renewal's role: record the intent, never activate anything.
    Activation only happens via activate_purchase, called from a
    verified payment callback."""
    try:
        offer = Offer.objects.select_for_update().get(pk=offer_id, merchant=merchant)
    except Offer.DoesNotExist as exc:
        raise PromotionError("Offer not found.") from exc

    if PromotionPurchase.objects.filter(offer=offer, status=PromotionPurchase.Status.PENDING).exists():
        raise PromotionError("A promotion payment for this offer is already pending.")

    try:
        purchase = PromotionPurchase.objects.create(merchant=merchant, offer=offer, package=package)
    except ValidationError as exc:
        raise PromotionError("; ".join(exc.messages) if hasattr(exc, "messages") else str(exc))
    return purchase


@transaction.atomic
def activate_purchase(purchase: PromotionPurchase) -> PromotionPurchase:
    """The only path that boosts an offer's visibility — called
    exclusively from a verified payment success, same discipline as
    subscriptions.services.confirm_payment."""
    purchase = PromotionPurchase.objects.select_for_update().get(pk=purchase.pk)
    if purchase.status != PromotionPurchase.Status.PENDING:
        return purchase

    now = timezone.now()
    purchase.status = PromotionPurchase.Status.ACTIVE
    purchase.starts_at = now
    purchase.expires_at = now + timezone.timedelta(days=purchase.package.duration_days)
    purchase.save(update_fields=["status", "starts_at", "expires_at"])

    offer = Offer.objects.select_for_update().get(pk=purchase.offer_id)
    offer.visibility_score += purchase.package.visibility_boost
    offer.save(update_fields=["visibility_score"])
    return purchase


@transaction.atomic
def fail_purchase(purchase: PromotionPurchase) -> PromotionPurchase:
    purchase = PromotionPurchase.objects.select_for_update().get(pk=purchase.pk)
    if purchase.status != PromotionPurchase.Status.PENDING:
        return purchase
    purchase.status = PromotionPurchase.Status.FAILED
    purchase.save(update_fields=["status"])
    return purchase


@transaction.atomic
def expire_stale_promotions() -> int:
    stale = PromotionPurchase.objects.select_for_update().filter(
        status=PromotionPurchase.Status.ACTIVE, expires_at__lte=timezone.now()
    )
    count = 0
    for purchase in stale:
        purchase.status = PromotionPurchase.Status.EXPIRED
        purchase.save(update_fields=["status"])
        offer = Offer.objects.select_for_update().get(pk=purchase.offer_id)
        offer.visibility_score = max(0, offer.visibility_score - purchase.package.visibility_boost)
        offer.save(update_fields=["visibility_score"])
        count += 1
    return count
