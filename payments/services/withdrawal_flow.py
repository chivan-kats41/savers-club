import logging
from decimal import ROUND_HALF_UP, Decimal
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from core.services import withdrawal_fee_percent, withdrawal_minimum
from deliveries.models import RiderEarning

from ..models import LedgerEntry, Withdrawal, WithdrawalCallback
from .iotec_client import IotecPayError
from . import status as pstatus
from .iotec_disbursements import initiate_disbursement

logger = logging.getLogger("payments")


class WithdrawalError(ValidationError):
    pass


RESERVED_STATUSES = (Withdrawal.Status.PENDING, Withdrawal.Status.PROCESSING, Withdrawal.Status.COMPLETED)


def available_rider_balance(rider) -> Decimal:
    earned = RiderEarning.objects.filter(rider=rider).aggregate(total=Sum("net_amount"))["total"] or Decimal("0")
    reserved = Withdrawal.objects.filter(user=rider.user, status__in=RESERVED_STATUSES).aggregate(
        total=Sum("amount")
    )["total"] or Decimal("0")
    return earned - reserved


@transaction.atomic
def request_rider_withdrawal(rider, amount: Decimal, phone: str) -> Withdrawal:
    if amount is None or amount <= 0:
        raise WithdrawalError("Withdrawal amount must be positive.")

    minimum = withdrawal_minimum()
    if amount < minimum:
        raise WithdrawalError(f"Minimum withdrawal is UGX {minimum}.")

    # Lock this rider's earning + withdrawal rows so two concurrent
    # withdrawal requests can't both see the same "available" balance.
    list(RiderEarning.objects.select_for_update().filter(rider=rider))
    list(Withdrawal.objects.select_for_update().filter(user=rider.user))

    available = available_rider_balance(rider)
    if amount > available:
        raise WithdrawalError(f"Insufficient available balance (UGX {available} available).")

    fee_pct = withdrawal_fee_percent()
    fee = (amount * fee_pct / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    net_amount = amount - fee
    if net_amount <= 0:
        raise WithdrawalError("Withdrawal amount is too small after fees.")

    withdrawal = Withdrawal.objects.create(
        user=rider.user, source=Withdrawal.Source.RIDER_EARNINGS,
        amount=amount, fee=fee, net_amount=net_amount, phone=phone,
        status=Withdrawal.Status.PENDING,
    )

    try:
        initiate_disbursement(withdrawal)
    except IotecPayError as exc:
        withdrawal.status = Withdrawal.Status.FAILED
        withdrawal.save(update_fields=["status"])
        logger.error("ioTec disbursement initiation failed for withdrawal=%s: %s", withdrawal.pk, exc)
        raise WithdrawalError(f"Could not start withdrawal: {exc}")

    return withdrawal


@transaction.atomic
def process_disbursement_callback(payload: dict) -> Withdrawal | None:
    external_id = payload.get("externalId") or payload.get("external_id")
    provider_status = str(payload.get("status") or "").strip().lower()
    provider_transaction_id = str(payload.get("transactionId") or payload.get("provider_transaction_id") or "")

    withdrawal = None
    if external_id:
        try:
            withdrawal = Withdrawal.objects.select_for_update().filter(internal_reference=external_id).first()
        except (ValidationError, ValueError):
            withdrawal = None

    is_duplicate = False
    if withdrawal is not None:
        is_duplicate = WithdrawalCallback.objects.filter(
            withdrawal=withdrawal, provider_status=provider_status,
            provider_transaction_id=provider_transaction_id, processed=True,
        ).exists()

    WithdrawalCallback.objects.create(
        withdrawal=withdrawal,
        raw_payload=payload,
        provider_status=provider_status,
        provider_transaction_id=provider_transaction_id,
        processed=False,
        processing_notes=(
            "No matching withdrawal for externalId." if withdrawal is None
            else "Duplicate event — already processed." if is_duplicate
            else ""
        ),
    )

    if withdrawal is None:
        logger.warning("ioTec disbursement callback for unknown externalId=%s", external_id)
        return None

    if is_duplicate:
        WithdrawalCallback.objects.filter(withdrawal=withdrawal, processed=False).update(processed=True)
        return withdrawal

    if withdrawal.status in Withdrawal.TERMINAL_STATUSES:
        WithdrawalCallback.objects.filter(withdrawal=withdrawal, processed=False).update(
            processed=True, processing_notes="Withdrawal already in a terminal state; no-op."
        )
        return withdrawal

    outcome = pstatus.classify(provider_status)

    if outcome == pstatus.SUCCESS:
        withdrawal.status = Withdrawal.Status.COMPLETED
        withdrawal.provider_transaction_id = provider_transaction_id or withdrawal.provider_transaction_id
        withdrawal.completed_at = timezone.now()
        withdrawal.save(update_fields=["status", "provider_transaction_id", "completed_at"])

        LedgerEntry.objects.create(
            payment=None, user=withdrawal.user, direction=LedgerEntry.Direction.DEBIT,
            amount=withdrawal.amount, fee=withdrawal.fee, net_amount=withdrawal.net_amount,
            reference=str(withdrawal.internal_reference),
        )

        from notifications.services.dispatch import notify

        notify(
            withdrawal.user, "withdrawal", "Withdrawal successful",
            f"UGX {withdrawal.net_amount:,.0f} has been sent to {withdrawal.phone}.",
        )
    elif outcome == pstatus.FAILED:
        withdrawal.status = Withdrawal.Status.FAILED
        withdrawal.save(update_fields=["status"])
        # Reservation releases naturally: available_rider_balance() only
        # counts PENDING/PROCESSING/COMPLETED, and FAILED is neither.

        from notifications.services.dispatch import notify

        notify(
            withdrawal.user, "withdrawal", "Withdrawal failed",
            f"Your withdrawal of UGX {withdrawal.amount:,.0f} could not be completed. The funds remain in your balance.",
        )

        recent_failures = Withdrawal.objects.filter(
            user=withdrawal.user, status=Withdrawal.Status.FAILED,
            created_at__gte=timezone.now() - timedelta(hours=24),
        ).count()
        if recent_failures >= 3:
            from core.services import record_risk_event

            record_risk_event(
                "repeated_withdrawal_failures", user=withdrawal.user,
                metadata={"failures_24h": recent_failures},
            )
    elif outcome == pstatus.SENT:
        withdrawal.status = Withdrawal.Status.PROCESSING
        withdrawal.save(update_fields=["status"])
    else:
        logger.info("ioTec status %r for withdrawal=%s: still in progress.", provider_status, withdrawal.pk)

    WithdrawalCallback.objects.filter(withdrawal=withdrawal, processed=False).update(processed=True)
    return withdrawal
