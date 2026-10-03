import logging
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from subscriptions.services import confirm_payment as confirm_subscription_payment
from subscriptions.services import initiate_renewal

from ..models import LedgerEntry, Payment, PaymentCallback
from .iotec_client import IotecPayError
from . import status as pstatus
from .iotec_collections import initiate_card_collection, initiate_mobile_money_collection

logger = logging.getLogger("payments")


class PaymentError(ValidationError):
    pass


def _initiate_collection(payment: Payment, method: str) -> None:
    try:
        if method == Payment.Method.MOBILE_MONEY:
            initiate_mobile_money_collection(payment)
        else:
            initiate_card_collection(payment)
    except IotecPayError as exc:
        payment.status = Payment.Status.FAILED
        payment.save(update_fields=["status"])
        logger.error("ioTec collection initiation failed for payment=%s: %s", payment.pk, exc)
        raise PaymentError(f"Could not start payment: {exc}")


@transaction.atomic
def initiate_subscription_payment(member, method: str, payer_phone: str = "", payer_email: str = "") -> Payment:
    """The only entry point for actually paying for a subscription. Opens
    a pending SubscriptionPayment (Phase 4's guard against double-renewal
    still applies), wraps it in a Payment, then calls ioTec. Never marks
    anything successful itself — see process_collection_callback."""
    if method == Payment.Method.MOBILE_MONEY and not payer_phone:
        raise PaymentError("A phone number is required for mobile money.")
    if method == Payment.Method.CARD and not payer_email:
        raise PaymentError("An email is required for card payment.")

    try:
        sub_payment = initiate_renewal(member)
    except ValidationError as exc:
        raise PaymentError("; ".join(exc.messages) if hasattr(exc, "messages") else str(exc))

    payment = Payment.objects.create(
        purpose=Payment.Purpose.SUBSCRIPTION,
        subscription_payment=sub_payment,
        user=member.user,
        method=method,
        amount=sub_payment.amount,
        payer_phone=payer_phone,
        payer_email=payer_email,
        status=Payment.Status.CREATED,
    )
    _initiate_collection(payment, method)
    return payment


@transaction.atomic
def initiate_promotion_payment(merchant, offer_id: int, package, method: str, payer_phone: str = "", payer_email: str = "") -> Payment:
    """Same discipline as initiate_subscription_payment: opens a PENDING
    PromotionPurchase, wraps it in a Payment, calls ioTec. Never boosts
    the offer's visibility itself — only process_collection_callback,
    via promotions.services.activate_purchase, does that."""
    if method == Payment.Method.MOBILE_MONEY and not payer_phone:
        raise PaymentError("A phone number is required for mobile money.")
    if method == Payment.Method.CARD and not payer_email:
        raise PaymentError("An email is required for card payment.")

    from promotions.services import PromotionError, create_pending_purchase

    try:
        purchase = create_pending_purchase(merchant, offer_id, package)
    except PromotionError as exc:
        raise PaymentError("; ".join(exc.messages) if hasattr(exc, "messages") else str(exc))

    payment = Payment.objects.create(
        purpose=Payment.Purpose.PROMOTION,
        promotion_purchase=purchase,
        user=merchant.user,
        method=method,
        amount=package.price,
        payer_phone=payer_phone,
        payer_email=payer_email,
        status=Payment.Status.CREATED,
    )
    _initiate_collection(payment, method)
    return payment


@transaction.atomic
def process_collection_callback(payload: dict) -> Payment | None:
    """Basic callback processing: idempotent (a payment already in a
    terminal state is left alone), records every callback received
    whether or not it maps to a known payment. Signature/replay-token
    verification, duplicate-event-id tracking, and the reconciliation
    sweep for stuck PENDING payments are hardened in Phase 8 — this is
    enough to safely drive the collection flow to completion now.
    """
    external_id = payload.get("externalId") or payload.get("external_id")
    provider_status = str(payload.get("status") or "").strip().lower()
    provider_transaction_id = str(payload.get("transactionId") or payload.get("provider_transaction_id") or "")

    payment = None
    if external_id:
        try:
            payment = Payment.objects.select_for_update().filter(internal_reference=external_id).first()
        except (ValidationError, ValueError):
            # Malformed externalId (not a valid UUID) — treat exactly like
            # "no matching payment" rather than crashing the endpoint.
            payment = None

    is_duplicate_event = False
    if payment is not None:
        is_duplicate_event = PaymentCallback.objects.filter(
            payment=payment, provider_status=provider_status,
            provider_transaction_id=provider_transaction_id, processed=True,
        ).exists()

    PaymentCallback.objects.create(
        payment=payment,
        raw_payload=payload,
        provider_status=provider_status,
        provider_transaction_id=provider_transaction_id,
        processed=False,
        processing_notes=(
            "No matching payment for externalId." if payment is None
            else "Duplicate event — already processed." if is_duplicate_event
            else ""
        ),
    )

    if payment is None:
        logger.warning("ioTec callback for unknown externalId=%s", external_id)
        return None

    if is_duplicate_event:
        # Explicit duplicate-event protection, layered on top of the
        # terminal-status guard below (defense in depth, per spec section 12).
        PaymentCallback.objects.filter(payment=payment, processed=False).update(processed=True)
        return payment

    if payment.status in Payment.TERMINAL_STATUSES:
        # Idempotency: a SUCCESS/FAILED payment must never be reprocessed,
        # even if ioTec redelivers the callback.
        PaymentCallback.objects.filter(payment=payment, processed=False).update(
            processed=True, processing_notes="Payment already in a terminal state; no-op."
        )
        return payment

    outcome = pstatus.classify(provider_status)

    if outcome == pstatus.SUCCESS:
        payment.status = Payment.Status.SUCCESS
        payment.provider_transaction_id = provider_transaction_id or payment.provider_transaction_id
        payment.save(update_fields=["status", "provider_transaction_id"])

        LedgerEntry.objects.create(
            payment=payment, user=payment.user, direction=LedgerEntry.Direction.CREDIT,
            amount=payment.amount, fee=0, net_amount=payment.amount,
            reference=str(payment.internal_reference),
        )

        if payment.subscription_payment_id:
            confirm_subscription_payment(
                payment.subscription_payment, success=True, provider_transaction_id=payment.provider_transaction_id
            )

        if payment.promotion_purchase_id:
            from promotions.services import activate_purchase

            activate_purchase(payment.promotion_purchase)

        from notifications.services.dispatch import notify

        if payment.purpose == Payment.Purpose.PROMOTION:
            notify(
                payment.user, "offer", "Promotion active",
                f"Your promotion payment of UGX {payment.amount:,.0f} was successful. The offer is now boosted.",
            )
        else:
            notify(
                payment.user, "subscription_payment", "Payment successful",
                f"Your payment of UGX {payment.amount:,.0f} was successful. Your subscription is now active.",
            )

    elif outcome == pstatus.FAILED:
        payment.status = Payment.Status.FAILED
        payment.save(update_fields=["status"])
        if payment.subscription_payment_id:
            confirm_subscription_payment(payment.subscription_payment, success=False)

        if payment.promotion_purchase_id:
            from promotions.services import fail_purchase

            fail_purchase(payment.promotion_purchase)

        from notifications.services.dispatch import notify

        purpose_label = "promotion" if payment.purpose == Payment.Purpose.PROMOTION else "subscription"
        notify(
            payment.user, "subscription_payment" if purpose_label == "subscription" else "offer", "Payment failed",
            f"Your {purpose_label} payment of UGX {payment.amount:,.0f} could not be completed. Please try again.",
        )

        recent_failures = Payment.objects.filter(
            user=payment.user, status=Payment.Status.FAILED,
            created_at__gte=timezone.now() - timedelta(hours=24),
        ).count()
        if recent_failures >= 3:
            from core.services import record_risk_event

            record_risk_event(
                "repeated_payment_failures", user=payment.user,
                metadata={"failures_24h": recent_failures},
            )

    elif outcome == pstatus.SENT:
        payment.status = Payment.Status.SENT_TO_VENDOR
        payment.save(update_fields=["status"])

    else:
        # Pending / AwaitingApproval / Scheduled / anything unknown: nothing to do yet.
        logger.info("ioTec status %r for payment=%s: still in progress.", provider_status, payment.pk)

    PaymentCallback.objects.filter(payment=payment, processed=False).update(processed=True)
    return payment
