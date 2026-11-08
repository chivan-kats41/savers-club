from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import Subscription, SubscriptionEvent, SubscriptionPayment, SubscriptionPlan


class SubscriptionError(ValidationError):
    """Raised for business-rule violations (e.g. renewing while a payment
    is already pending). Views translate this into a 400 API error."""


def get_default_plan() -> SubscriptionPlan:
    plan = SubscriptionPlan.objects.filter(is_active=True).order_by("price").first()
    if plan is None:
        raise SubscriptionError("No active subscription plan is configured.")
    return plan


# A pending SubscriptionPayment with no provider Payment behind it can never complete by itself (it was
# opened without calling a payment provider). After this long it is closed so it cannot block the member.
ORPHAN_GRACE = timedelta(minutes=15)
_OPEN_PROVIDER_STATES = {"created", "pending", "sent_to_vendor"}


def close_orphan_payments(member) -> int:
    """Close pending SubscriptionPayments that have NO provider payment behind them, right now.

    The normal flow creates the SubscriptionPayment and its provider Payment in one transaction, so a committed
    "pending with nothing behind it" can only be a leftover (the legacy /subscription/renew/ endpoint, or a crash). It
    can never finish, so a member who is starting a real payment must not be told "already pending" for 15 minutes
    because of it. Must be called inside a transaction."""
    closed = 0
    subscription = (Subscription.objects.select_for_update().filter(member=member)
                    .exclude(status=Subscription.Status.CANCELLED).order_by("-created_at").first())
    if subscription is None:
        return 0
    for pending in subscription.payments.filter(status=SubscriptionPayment.Status.PENDING):
        if getattr(pending, "provider_payment", None) is None:
            pending.status = SubscriptionPayment.Status.FAILED
            pending.save(update_fields=["status"])
            SubscriptionEvent.objects.create(
                subscription=subscription, event_type="payment_abandoned", metadata={"payment_id": str(pending.pk)})
            closed += 1
    return closed


def _block_if_payment_in_flight(subscription: Subscription) -> None:
    """Raise if a real payment for this subscription is still genuinely in flight; quietly close
    pending payments that can never finish. A payment parked for manual review (REQUIRES_REVIEW) does not
    block a new purchase: if it later turns out to have succeeded, it simply extends the period."""
    now = timezone.now()
    for pending in subscription.payments.filter(status=SubscriptionPayment.Status.PENDING):
        provider = getattr(pending, "provider_payment", None)
        if provider is None:
            if now - pending.created_at > ORPHAN_GRACE:
                pending.status = SubscriptionPayment.Status.FAILED
                pending.save(update_fields=["status"])
                SubscriptionEvent.objects.create(
                    subscription=subscription, event_type="payment_abandoned", metadata={"payment_id": str(pending.pk)}
                )
                continue
            raise SubscriptionError("A payment for this subscription is already pending.")
        if provider.status in _OPEN_PROVIDER_STATES:
            raise SubscriptionError("A payment for this subscription is already pending.")


@transaction.atomic
def initiate_renewal(member, plan: SubscriptionPlan | None = None) -> SubscriptionPayment:
    """Opens a new SubscriptionPayment for `plan` (default: the cheapest active plan) on the member's
    single subscription, creating that subscription if needed. Does NOT contact any payment provider and
    does NOT activate anything: only a confirmed payment (confirm_payment) does that."""
    plan = plan or get_default_plan()
    if not plan.is_active:
        raise SubscriptionError("That subscription plan is not available.")

    # One subscription per member, whatever plan they pick: switching plan never creates a second active one.
    subscription = (
        Subscription.objects.select_for_update()
        .filter(member=member)
        .exclude(status=Subscription.Status.CANCELLED)
        .order_by("-created_at")
        .first()
    )

    if subscription is not None:
        _block_if_payment_in_flight(subscription)
    else:
        subscription = Subscription.objects.create(member=member, plan=plan, status=Subscription.Status.PENDING)
        SubscriptionEvent.objects.create(subscription=subscription, event_type="created")

    payment = SubscriptionPayment.objects.create(
        subscription=subscription, plan=plan, amount=plan.price, status=SubscriptionPayment.Status.PENDING
    )
    SubscriptionEvent.objects.create(
        subscription=subscription,
        event_type="renewal_initiated",
        metadata={"payment_id": str(payment.pk), "amount": str(plan.price), "plan": plan.code},
    )
    return payment


@transaction.atomic
def confirm_payment(payment: SubscriptionPayment, success: bool, provider_transaction_id: str = "") -> Subscription:
    """The ONLY path that activates a subscription. Called exclusively from a verified payment-provider
    callback / reconciliation job, never directly from a frontend request."""
    payment = SubscriptionPayment.objects.select_for_update().select_related("plan").get(pk=payment.pk)
    if payment.status != SubscriptionPayment.Status.PENDING:
        raise SubscriptionError("Payment is not pending; refusing to process it again.")

    subscription = Subscription.objects.select_for_update().get(pk=payment.subscription_id)

    is_first_ever_activation = not SubscriptionPayment.objects.filter(
        subscription__member=subscription.member, status=SubscriptionPayment.Status.SUCCESS
    ).exists()

    if success:
        payment.status = SubscriptionPayment.Status.SUCCESS
        payment.provider_transaction_id = provider_transaction_id
        payment.save(update_fields=["status", "provider_transaction_id"])

        # The plan the member paid for becomes their plan (this is how monthly <-> quarterly <-> yearly switches happen).
        plan = payment.plan or subscription.plan
        now = timezone.now()
        period_start = (
            subscription.current_period_end
            if subscription.is_currently_active
            else now
        )
        subscription.plan = plan
        subscription.status = Subscription.Status.ACTIVE
        subscription.current_period_start = period_start
        subscription.current_period_end = period_start + timedelta(days=plan.period_days)
        subscription.save(update_fields=["plan", "status", "current_period_start", "current_period_end"])
        SubscriptionEvent.objects.create(
            subscription=subscription,
            event_type="payment_success",
            metadata={"payment_id": str(payment.pk), "plan": plan.code},
        )

        if is_first_ever_activation and subscription.member.referred_by_id:
            from members.models import ReferralReward
            from core.services import get_setting_decimal
            from decimal import Decimal

            already_rewarded = ReferralReward.objects.filter(referred_member=subscription.member).exists()
            if not already_rewarded:
                ReferralReward.objects.create(
                    referrer=subscription.member.referred_by,
                    referred_member=subscription.member,
                    amount=get_setting_decimal("referral.reward_ugx", Decimal("500")),
                )
    else:
        payment.status = SubscriptionPayment.Status.FAILED
        payment.provider_transaction_id = provider_transaction_id
        payment.save(update_fields=["status", "provider_transaction_id"])
        SubscriptionEvent.objects.create(
            subscription=subscription,
            event_type="payment_failed",
            metadata={"payment_id": str(payment.pk)},
        )

    return subscription


@transaction.atomic
def pause_subscription(member) -> Subscription:
    subscription = (
        Subscription.objects.select_for_update()
        .filter(member=member, status=Subscription.Status.ACTIVE)
        .order_by("-created_at")
        .first()
    )
    if subscription is None:
        raise SubscriptionError("No active subscription to pause.")
    subscription.status = Subscription.Status.PAUSED
    subscription.save(update_fields=["status"])
    SubscriptionEvent.objects.create(subscription=subscription, event_type="paused")
    return subscription


@transaction.atomic
def resume_subscription(member) -> Subscription:
    subscription = (
        Subscription.objects.select_for_update()
        .filter(member=member, status=Subscription.Status.PAUSED)
        .order_by("-created_at")
        .first()
    )
    if subscription is None:
        raise SubscriptionError("No paused subscription to resume.")
    subscription.status = Subscription.Status.ACTIVE
    subscription.save(update_fields=["status"])
    SubscriptionEvent.objects.create(subscription=subscription, event_type="resumed")
    return subscription


@transaction.atomic
def expire_stale_subscriptions() -> int:
    """Sweep ACTIVE subscriptions whose current_period_end has passed.
    Iterates (rather than a bulk .update()) so each transition still
    gets its SubscriptionEvent audit row."""
    from django.utils import timezone

    stale = Subscription.objects.select_for_update().filter(
        status=Subscription.Status.ACTIVE, current_period_end__lte=timezone.now()
    )
    count = 0
    for subscription in stale:
        subscription.status = Subscription.Status.EXPIRED
        subscription.save(update_fields=["status"])
        SubscriptionEvent.objects.create(subscription=subscription, event_type="expired")
        count += 1
    return count
