from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Subscription, SubscriptionEvent, SubscriptionPayment, SubscriptionPlan


class SubscriptionError(ValidationError):
    """Raised for business-rule violations (e.g. renewing while a payment
    is already pending). Views translate this into a 400 API error."""


def get_default_plan() -> SubscriptionPlan:
    plan = SubscriptionPlan.objects.filter(is_active=True).order_by("price").first()
    if plan is None:
        raise SubscriptionError("No active subscription plan is configured.")
    return plan


@transaction.atomic
def initiate_renewal(member, plan: SubscriptionPlan | None = None) -> SubscriptionPayment:
    """Creates (or reuses) a Subscription in PENDING/expired state and
    opens a new SubscriptionPayment for it. Does NOT contact any payment
    provider yet — that's Phase 7. Does NOT activate the subscription —
    only a confirmed payment (via confirm_payment, called from a real
    callback in Phase 7) does that.
    """
    plan = plan or get_default_plan()

    subscription = (
        Subscription.objects.select_for_update()
        .filter(member=member, plan=plan)
        .exclude(status=Subscription.Status.CANCELLED)
        .order_by("-created_at")
        .first()
    )

    if subscription and subscription.payments.filter(status=SubscriptionPayment.Status.PENDING).exists():
        raise SubscriptionError("A payment for this subscription is already pending.")

    if subscription is None:
        subscription = Subscription.objects.create(member=member, plan=plan, status=Subscription.Status.PENDING)
        SubscriptionEvent.objects.create(subscription=subscription, event_type="created")

    payment = SubscriptionPayment.objects.create(
        subscription=subscription, amount=plan.price, status=SubscriptionPayment.Status.PENDING
    )
    SubscriptionEvent.objects.create(
        subscription=subscription,
        event_type="renewal_initiated",
        metadata={"payment_id": str(payment.pk), "amount": str(plan.price)},
    )
    return payment


@transaction.atomic
def confirm_payment(payment: SubscriptionPayment, success: bool, provider_transaction_id: str = "") -> Subscription:
    """The ONLY path that activates a subscription. In production this is
    called exclusively from a verified payment-provider callback/
    reconciliation job (Phase 7/8) — never directly from a frontend
    request. A dev-only management command exercises it manually until
    then, precisely so this activation logic is proven before ioTec is
    wired in.
    """
    payment = SubscriptionPayment.objects.select_for_update().get(pk=payment.pk)
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

        from django.utils import timezone
        from datetime import timedelta

        now = timezone.now()
        period_start = (
            subscription.current_period_end
            if subscription.is_currently_active
            else now
        )
        subscription.status = Subscription.Status.ACTIVE
        subscription.current_period_start = period_start
        subscription.current_period_end = period_start + timedelta(days=subscription.plan.period_days)
        subscription.save(update_fields=["status", "current_period_start", "current_period_end"])
        SubscriptionEvent.objects.create(
            subscription=subscription,
            event_type="payment_success",
            metadata={"payment_id": str(payment.pk)},
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
