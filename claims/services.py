from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from merchants.models import Merchant
from offers.models import Offer
from savings.models import SavingsRecord

from .models import ClaimEvent, OfferClaim


class ClaimError(ValidationError):
    """Business-rule violation while claiming/redeeming — views turn this
    into a 400 API error rather than a 500."""


MAX_REDEMPTION_ATTEMPTS = 5


@transaction.atomic
def claim_offer(member, offer_id: int) -> OfferClaim:
    offer = Offer.objects.select_for_update().select_related("merchant").get(pk=offer_id)

    if offer.status != Offer.Status.ACTIVE:
        raise ClaimError("This offer is not currently active.")
    if offer.is_expired:
        raise ClaimError("This offer has expired.")
    if offer.quantity <= 0:
        raise ClaimError("This offer is out of stock.")

    already_claimed = OfferClaim.objects.filter(
        member=member, offer=offer, status=OfferClaim.Status.CLAIMED
    ).exists()
    if already_claimed:
        raise ClaimError("You already have an active claim on this offer.")

    offer.quantity -= 1
    offer.save(update_fields=["quantity"])

    claim = OfferClaim.objects.create(
        member=member,
        offer=offer,
        expected_saving=offer.possible_saving,
        expires_at=timezone.now() + timezone.timedelta(hours=settings.CLAIM_CODE_EXPIRY_HOURS),
    )
    ClaimEvent.objects.create(claim=claim, event_type="claimed", actor=member.user)
    return claim


def redeem_claim(merchant: Merchant, code: str) -> OfferClaim:
    """NOTE: deliberately NOT wrapped in a single @transaction.atomic that
    also raises — earlier revision recorded the lockout/expiry audit rows
    then immediately raised ClaimError from inside one atomic block,
    which silently rolled back those very audit rows along with
    everything else (transaction.atomic rolls back its entire scope on
    ANY exception, not just DB errors). The state-mutating work below
    commits first (inside `with transaction.atomic()`); only after that
    block has exited normally do we raise, so a lockout/expiry outcome's
    audit trail actually persists.
    """
    lockout_triggered = False
    expired_triggered = False

    with transaction.atomic():
        try:
            claim = (
                OfferClaim.objects.select_for_update()
                .select_related("offer", "offer__merchant", "member")
                .get(code=code.strip().upper())
            )
        except OfferClaim.DoesNotExist as exc:
            raise ClaimError("Invalid claim code.") from exc

        if claim.offer.merchant_id != merchant.id:
            # Deliberately the same generic error as "not found" — never
            # confirm to a merchant that a code exists for a *different* shop.
            raise ClaimError("Invalid claim code.")

        if claim.status == OfferClaim.Status.REDEEMED:
            raise ClaimError("This code has already been redeemed.")

        if claim.status != OfferClaim.Status.CLAIMED:
            raise ClaimError(f"This code is {claim.get_status_display().lower()} and cannot be redeemed.")

        if claim.is_expired:
            claim.status = OfferClaim.Status.EXPIRED
            claim.save(update_fields=["status"])
            ClaimEvent.objects.create(claim=claim, event_type="expired_on_redemption_attempt", actor=merchant.user)
            expired_triggered = True
        else:
            claim.redemption_attempts += 1
            if claim.redemption_attempts > MAX_REDEMPTION_ATTEMPTS:
                claim.save(update_fields=["redemption_attempts"])
                ClaimEvent.objects.create(
                    claim=claim, event_type="redemption_locked_suspicious", actor=merchant.user
                )
                lockout_triggered = True
            else:
                claim.status = OfferClaim.Status.REDEEMED
                claim.redeemed_at = timezone.now()
                claim.redeemed_by = merchant.user
                claim.save(update_fields=["status", "redeemed_at", "redeemed_by", "redemption_attempts"])

                SavingsRecord.objects.create(
                    claim=claim,
                    member=claim.member,
                    merchant=merchant,
                    normal_price=claim.offer.normal_price,
                    member_price=claim.offer.member_price,
                    saving_amount=claim.expected_saving,
                )
                ClaimEvent.objects.create(claim=claim, event_type="redeemed", actor=merchant.user)

    # The atomic block above has now committed — anything written on the
    # lockout/expiry paths is durable, so it's now safe to raise.
    if expired_triggered:
        raise ClaimError("This code has expired.")

    if lockout_triggered:
        from core.services import record_risk_event

        record_risk_event(
            "claim_redemption_locked", user=merchant.user,
            metadata={"claim_code": claim.code, "attempts": claim.redemption_attempts},
        )
        raise ClaimError("Too many redemption attempts on this code. Contact support.")

    from notifications.services.dispatch import notify

    notify(
        claim.member.user, "claim", "You saved money!",
        f"You saved UGX {claim.expected_saving:,.0f} on {claim.offer.item_name} at {merchant.business_name}.",
    )
    return claim


@transaction.atomic
def cancel_claim(member, code: str) -> OfferClaim:
    try:
        claim = OfferClaim.objects.select_for_update().select_related("offer").get(
            code=code.strip().upper(), member=member
        )
    except OfferClaim.DoesNotExist as exc:
        raise ClaimError("Claim not found.") from exc

    if claim.status != OfferClaim.Status.CLAIMED:
        raise ClaimError("Only an active claim can be cancelled.")

    claim.status = OfferClaim.Status.CANCELLED
    claim.save(update_fields=["status"])

    offer = Offer.objects.select_for_update().get(pk=claim.offer_id)
    offer.quantity += 1
    offer.save(update_fields=["quantity"])

    ClaimEvent.objects.create(claim=claim, event_type="cancelled", actor=member.user)
    return claim


@transaction.atomic
def expire_stale_claims() -> int:
    """Sweep CLAIMED claims past their expiry, restocking the offer for
    each. Intended to run on a schedule (Celery beat, wired in Phase 10);
    exposed as a management command in the meantime."""
    stale = OfferClaim.objects.select_for_update().filter(
        status=OfferClaim.Status.CLAIMED, expires_at__lte=timezone.now()
    )
    count = 0
    for claim in stale:
        claim.status = OfferClaim.Status.EXPIRED
        claim.save(update_fields=["status"])
        offer = Offer.objects.select_for_update().get(pk=claim.offer_id)
        offer.quantity += 1
        offer.save(update_fields=["quantity"])
        ClaimEvent.objects.create(claim=claim, event_type="expired")
        count += 1
    return count
