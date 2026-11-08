import logging
from decimal import ROUND_HALF_UP, Decimal
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from core.services import withdrawal_daily_limit, withdrawal_fee_percent, withdrawal_minimum
from deliveries.models import RiderEarning

from ..models import LedgerEntry, Withdrawal, WithdrawalCallback
from .iotec_client import IotecPayError, IotecUncertainError
from . import status as pstatus
from .iotec_disbursements import initiate_disbursement

logger = logging.getLogger("payments")


class WithdrawalError(ValidationError):
    pass


RESERVED_STATUSES = (Withdrawal.Status.PENDING, Withdrawal.Status.PROCESSING, Withdrawal.Status.COMPLETED)


def available_rider_balance(rider) -> Decimal:
    """What the platform owes the rider: earnings, minus cash fares the rider already collected on delivery,
    minus withdrawals already requested. Can be negative (the rider holds more cash than they have earned)."""
    totals = RiderEarning.objects.filter(rider=rider).aggregate(net=Sum("net_amount"), cash=Sum("cash_collected"))
    earned = (totals["net"] or Decimal("0")) - (totals["cash"] or Decimal("0"))
    reserved = Withdrawal.objects.filter(
        user=rider.user, source=Withdrawal.Source.RIDER_EARNINGS, status__in=RESERVED_STATUSES
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    return earned - reserved


def available_referral_balance(member) -> Decimal:
    """Credited referral rewards not yet withdrawn."""
    from members.models import ReferralReward

    earned = ReferralReward.objects.filter(
        referrer=member, status=ReferralReward.Status.CREDITED
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    reserved = Withdrawal.objects.filter(
        user=member.user, source=Withdrawal.Source.REFERRAL_REWARDS, status__in=RESERVED_STATUSES
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    return earned - reserved


def _reserve_withdrawal(user, source: str, amount: Decimal, phone: str, lock_rows, balance_fn) -> Withdrawal:
    """Validate, lock and record the request. Committed BEFORE ioTec is called, so the reserved
    balance and the record survive whatever happens on the network."""
    from payments import config

    if amount is None or not amount.is_finite() or amount <= 0:
        raise WithdrawalError("Withdrawal amount must be a positive number.")
    if config.normalize_msisdn(phone) is None:
        raise WithdrawalError("Enter a valid MTN or Airtel number, e.g. 0772 123 456.")

    minimum = withdrawal_minimum()
    if amount < minimum:
        raise WithdrawalError(f"Minimum withdrawal is UGX {minimum}.")

    with transaction.atomic():
        # Lock this owner's earning + withdrawal rows so two concurrent
        # withdrawal requests can't both see the same "available" balance.
        lock_rows()
        list(Withdrawal.objects.select_for_update().filter(user=user, source=source))

        available = balance_fn()
        if amount > available:
            raise WithdrawalError(f"Insufficient available balance (UGX {max(available, Decimal('0'))} available).")

        # Rolling 24 h cap across every source (rider earnings + referral rewards). Failed/reversed ones don't count.
        from datetime import timedelta

        from django.db.models import Sum
        from django.utils import timezone

        taken = (Withdrawal.objects.filter(user=user, created_at__gte=timezone.now() - timedelta(hours=24))
                 .exclude(status__in=[Withdrawal.Status.FAILED, Withdrawal.Status.REVERSED])
                 .aggregate(total=Sum("amount"))["total"] or Decimal("0"))
        daily = withdrawal_daily_limit()
        if taken + amount > daily:
            room = max(daily - taken, Decimal("0"))
            raise WithdrawalError(
                f"Daily withdrawal limit reached. You can withdraw up to UGX {room:,.0f} more in the next 24 hours.")

        fee_pct = withdrawal_fee_percent()
        fee = (amount * fee_pct / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        net_amount = amount - fee
        if net_amount <= 0:
            raise WithdrawalError("Withdrawal amount is too small after fees.")

        return Withdrawal.objects.create(
            user=user, source=source,
            amount=amount, fee=fee, net_amount=net_amount, phone=phone,
            status=Withdrawal.Status.PENDING,
        )


def _send_withdrawal(withdrawal: Withdrawal) -> Withdrawal:
    try:
        initiate_disbursement(withdrawal)
    except IotecUncertainError as exc:
        # ioTec may already have sent the money. Keep the row PENDING (balance stays reserved so it
        # cannot be withdrawn twice); reconciliation looks it up by externalId and settles it.
        logger.warning("ioTec disbursement outcome unknown for withdrawal=%s: %s (left PENDING)", withdrawal.pk, exc)
    except IotecPayError as exc:
        # Definite rejection: nothing was sent. Persist FAILED, which releases the reserved balance.
        withdrawal.status = Withdrawal.Status.FAILED
        withdrawal.save(update_fields=["status"])
        logger.error("ioTec disbursement initiation failed for withdrawal=%s: %s", withdrawal.pk, exc)
        raise WithdrawalError(f"Could not start withdrawal: {exc}")
    return withdrawal


def request_rider_withdrawal(rider, amount: Decimal, phone: str) -> Withdrawal:
    withdrawal = _reserve_withdrawal(
        rider.user, Withdrawal.Source.RIDER_EARNINGS, amount, phone,
        lock_rows=lambda: list(RiderEarning.objects.select_for_update().filter(rider=rider)),
        balance_fn=lambda: available_rider_balance(rider),
    )
    return _send_withdrawal(withdrawal)


def request_referral_withdrawal(member, amount: Decimal, phone: str) -> Withdrawal:
    """Cash out credited referral rewards to mobile money, with the same reservation / fee / reconciliation
    safety as rider withdrawals."""
    from members.models import ReferralReward

    withdrawal = _reserve_withdrawal(
        member.user, Withdrawal.Source.REFERRAL_REWARDS, amount, phone,
        lock_rows=lambda: list(ReferralReward.objects.select_for_update().filter(referrer=member)),
        balance_fn=lambda: available_referral_balance(member),
    )
    return _send_withdrawal(withdrawal)


def fail_unsent_withdrawal(withdrawal: Withdrawal) -> bool:
    """Close a withdrawal ioTec has proven (404) it never received. Returns True if closed."""
    with transaction.atomic():
        locked = Withdrawal.objects.select_for_update().get(pk=withdrawal.pk)
        if locked.status != Withdrawal.Status.PENDING or locked.provider_transaction_id:
            return False
        locked.status = Withdrawal.Status.FAILED
        locked.save(update_fields=["status"])
    withdrawal.refresh_from_db()
    return True


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
