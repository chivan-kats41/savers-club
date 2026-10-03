from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from core.services import get_setting_decimal
from merchants.models import Merchant, MerchantVerification
from riders.models import Rider, RiderVerification

from .models import Agent, AgentEarning, PriceRecord


class AgentError(ValidationError):
    pass


def merchant_verification_fee() -> Decimal:
    return get_setting_decimal("agent.merchant_verification_fee_ugx", Decimal("500"))


def rider_verification_fee() -> Decimal:
    return get_setting_decimal("agent.rider_verification_fee_ugx", Decimal("500"))


@transaction.atomic
def verify_merchant(agent: Agent, merchant_id: int, outcome: str, checklist: dict, notes: str = "") -> Merchant:
    try:
        merchant = Merchant.objects.select_for_update().get(pk=merchant_id)
    except Merchant.DoesNotExist as exc:
        raise AgentError("Merchant not found.") from exc

    if not agent.covers_area(merchant.area_id):
        raise AgentError("This merchant is outside your assigned areas.")

    if outcome not in Merchant.Status.values:
        raise AgentError("Invalid verification outcome.")

    MerchantVerification.objects.create(
        merchant=merchant, performed_by=agent.user, outcome=outcome, checklist=checklist, notes=notes
    )

    merchant.status = outcome
    if outcome == Merchant.Status.VERIFIED:
        merchant.verified_by = agent.user
        merchant.verified_at = timezone.now()
        AgentEarning.objects.create(
            agent=agent, source=AgentEarning.Source.MERCHANT_VERIFICATION,
            amount=merchant_verification_fee(), reference=f"merchant:{merchant.id}",
        )
    merchant.save(update_fields=["status", "verified_by", "verified_at"])
    return merchant


@transaction.atomic
def verify_rider(agent: Agent, rider_id: int, outcome: str, checklist: dict, notes: str = "") -> Rider:
    try:
        rider = Rider.objects.select_for_update().get(pk=rider_id)
    except Rider.DoesNotExist as exc:
        raise AgentError("Rider not found.") from exc

    if not agent.covers_area(rider.area_id):
        raise AgentError("This rider is outside your assigned areas.")

    if outcome not in Rider.Status.values:
        raise AgentError("Invalid verification outcome.")

    RiderVerification.objects.create(
        rider=rider, performed_by=agent.user, outcome=outcome, checklist=checklist, notes=notes
    )

    rider.status = outcome
    if outcome == Rider.Status.VERIFIED:
        rider.verified_by = agent.user
        rider.verified_at = timezone.now()
        AgentEarning.objects.create(
            agent=agent, source=AgentEarning.Source.RIDER_VERIFICATION,
            amount=rider_verification_fee(), reference=f"rider:{rider.id}",
        )
    rider.save(update_fields=["status", "verified_by", "verified_at"])
    return rider


def submit_price(agent: Agent, area, category, item_name: str, price) -> PriceRecord:
    if not agent.covers_area(area.id):
        raise AgentError("You can only submit prices for your assigned areas.")
    if price is None or price <= 0:
        raise AgentError("Price must be positive.")
    return PriceRecord.objects.create(agent=agent, area=area, category=category, item_name=item_name, price=price)


@transaction.atomic
def approve_offer(agent: Agent, offer_id: int) -> "Offer":
    from offers.models import Offer

    try:
        offer = Offer.objects.select_for_update().get(pk=offer_id)
    except Offer.DoesNotExist as exc:
        raise AgentError("Offer not found.") from exc

    if not agent.covers_area(offer.area_id):
        raise AgentError("This offer is outside your assigned areas.")
    if offer.status != offer.Status.PENDING:
        raise AgentError("Only a pending offer can be approved.")

    offer.status = offer.Status.ACTIVE
    offer.save(update_fields=["status"])
    return offer


@transaction.atomic
def reject_offer(agent: Agent, offer_id: int, reason: str = "") -> "Offer":
    from offers.models import Offer

    try:
        offer = Offer.objects.select_for_update().get(pk=offer_id)
    except Offer.DoesNotExist as exc:
        raise AgentError("Offer not found.") from exc

    if not agent.covers_area(offer.area_id):
        raise AgentError("This offer is outside your assigned areas.")
    if offer.status != offer.Status.PENDING:
        raise AgentError("Only a pending offer can be rejected.")

    offer.status = offer.Status.REJECTED
    offer.save(update_fields=["status"])
    return offer
