from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from merchants.models import Merchant
from offers.models import Offer
from savings.models import SavingsRecord

from .models import ClaimEvent, OfferClaim


class ClaimError(ValidationError):
    """Business-rule violation while claiming/redeeming — views turn this
    into a 400 API error rather than a 500."""


MAX_REDEMPTION_ATTEMPTS = 5

# Wrong-code guessing guard. A claim code is 6 characters, so a merchant (or someone with a stolen merchant session)
# could otherwise sit and try codes all day. The per-claim counter below can never trigger for a CLAIMED code (the
# first valid attempt redeems it), and a wrong code belongs to no claim, so the failures are counted per MERCHANT:
# after REDEEM_FAIL_LIMIT wrong/foreign codes in REDEEM_FAIL_WINDOW seconds, redeeming pauses for the rest of the window.
REDEEM_FAIL_LIMIT = 8
REDEEM_FAIL_WINDOW = 15 * 60


def _redeem_fail_key(merchant) -> str:
    return f"claims:redeem-fail:{merchant.pk}"


def _redeem_locked(merchant) -> bool:
    return (cache.get(_redeem_fail_key(merchant)) or 0) >= REDEEM_FAIL_LIMIT


def _register_bad_code(merchant) -> None:
    key = _redeem_fail_key(merchant)
    if cache.add(key, 1, timeout=REDEEM_FAIL_WINDOW):
        return
    try:
        cache.incr(key)
    except ValueError:                       # expired between add and incr
        cache.add(key, 1, timeout=REDEEM_FAIL_WINDOW)


def _has_active_subscription(member) -> bool:
    from subscriptions.models import Subscription

    return Subscription.objects.filter(
        member=member, status=Subscription.Status.ACTIVE, current_period_end__gt=timezone.now()
    ).exists()


@transaction.atomic
def claim_offer(member, offer_id: int) -> OfferClaim:
    if getattr(settings, "REQUIRE_SUBSCRIPTION_TO_CLAIM", True) and not _has_active_subscription(member):
        raise ClaimError("An active subscription is required to claim offers. Choose a plan to subscribe.")

    try:
        offer = Offer.objects.select_for_update().select_related("merchant").get(pk=offer_id)
    except Offer.DoesNotExist as exc:
        raise ClaimError("This offer does not exist.") from exc

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

    claim = None
    for _ in range(10):  # a random code can (rarely) collide with an existing one: draw again
        try:
            with transaction.atomic():
                claim = OfferClaim.objects.create(
                    member=member,
                    offer=offer,
                    expected_saving=offer.possible_saving,
                    expires_at=timezone.now() + timezone.timedelta(hours=settings.CLAIM_CODE_EXPIRY_HOURS),
                )
            break
        except IntegrityError:
            continue
    if claim is None:
        raise ClaimError("Could not generate a claim code. Please try again.")
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

    if _redeem_locked(merchant):
        from core.services import record_risk_event

        record_risk_event("claim_code_guessing", user=merchant.user, metadata={"merchant_id": merchant.pk})
        raise ClaimError("Too many wrong codes. Redeeming is paused for 15 minutes; please check the code with the customer.")

    with transaction.atomic():
        try:
            claim = (
                OfferClaim.objects.select_for_update()
                .select_related("offer", "offer__merchant", "member")
                .get(code=code.strip().upper())
            )
        except OfferClaim.DoesNotExist as exc:
            _register_bad_code(merchant)
            raise ClaimError("Invalid claim code.") from exc

        if claim.offer.merchant_id != merchant.id:
            # Deliberately the same generic error as "not found" — never
            # confirm to a merchant that a code exists for a *different* shop.
            _register_bad_code(merchant)
            raise ClaimError("Invalid claim code.")

        if claim.status == OfferClaim.Status.REDEEMED:
            raise ClaimError("This code has already been redeemed.")

        if claim.status != OfferClaim.Status.CLAIMED:
            raise ClaimError(f"This code is {claim.get_status_display().lower()} and cannot be redeemed.")

        if claim.is_expired:
            claim.status = OfferClaim.Status.EXPIRED
            claim.save(update_fields=["status"])
            # Put the unit back on the shelf, exactly as the scheduled sweep does for claims it expires.
            offer = Offer.objects.select_for_update().get(pk=claim.offer_id)
            offer.quantity += 1
            offer.save(update_fields=["quantity"])
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

    cache.delete(_redeem_fail_key(merchant))          # a good redemption clears the wrong-code streak

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
