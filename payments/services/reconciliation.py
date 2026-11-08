import logging
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from core.services import reconciliation_timeout_minutes

from ..models import Payment, Withdrawal
from .iotec_client import IotecNotFound, IotecPayError
from . import status as pstatus
from .iotec_collections import get_collection_by_external_id, get_collection_status
from .iotec_disbursements import get_disbursement_by_external_id, get_disbursement_status
from .payment_flow import fail_unsent_payment, process_collection_callback
from .withdrawal_flow import fail_unsent_withdrawal, process_disbursement_callback

logger = logging.getLogger("payments")


def _age_minutes(instance) -> float:
    return (timezone.now() - instance.created_at).total_seconds() / 60


OPEN_PAYMENT_STATUSES = (Payment.Status.CREATED, Payment.Status.PENDING, Payment.Status.SENT_TO_VENDOR)

# A payment parked as REQUIRES_REVIEW (no answer from ioTec within the timeout) is NOT dead: the customer may approve
# the prompt late, or ioTec may answer late. Keep asking ioTec for a while so a late "Success" still activates what
# was paid for and a late "Failed" releases the member, instead of leaving both stuck forever.
REVIEW_RECHECK_DAYS = 14


def is_recheckable(payment: Payment) -> bool:
    if payment.status in OPEN_PAYMENT_STATUSES:
        return True
    return (payment.status == Payment.Status.REQUIRES_REVIEW
            and payment.created_at >= timezone.now() - timedelta(days=REVIEW_RECHECK_DAYS))

# ioTec answering 404 for our externalId only proves the request never arrived once we have waited
# long enough for a slow, in-flight request to have landed.
NOT_FOUND_GRACE_MINUTES = 10


def fetch_collection_state(payment: Payment) -> dict:
    """Ask ioTec (the only authority) what happened. Prefers the transaction id; falls back to our own
    externalId if the initiation response was lost."""
    if payment.provider_transaction_id:
        return get_collection_status(payment.provider_transaction_id)
    return get_collection_by_external_id(str(payment.internal_reference))


def _amount_matches(expected, data: dict) -> bool:
    """A "Success" for a different amount/currency than we asked for must never activate anything."""
    from decimal import Decimal, InvalidOperation

    got = data.get("amount")
    if got is None:
        return True
    try:
        if Decimal(str(got)) != Decimal(expected):
            return False
    except InvalidOperation:
        return False
    cur = data.get("currency")
    from payments import config
    return not cur or str(cur).upper() == config.currency()


def apply_collection_state(payment: Payment, data: dict) -> Payment:
    """Apply a provider-reported state (from the status API) to a Payment."""
    if pstatus.classify(data.get("status")) == pstatus.SUCCESS and not _amount_matches(payment.amount, data):
        already_flagged = payment.status == Payment.Status.REQUIRES_REVIEW
        if already_flagged:
            return payment                      # parked for a human already; don't log/record it again every sweep
        logger.error("ioTec reported SUCCESS for payment=%s with a different amount/currency (%s %s vs %s): flagged for review.",
                     payment.pk, data.get("amount"), data.get("currency"), payment.amount)
        Payment.objects.filter(pk=payment.pk).exclude(status__in=Payment.TERMINAL_STATUSES).update(
            status=Payment.Status.REQUIRES_REVIEW)
        try:
            from core.services import record_risk_event
            record_risk_event("payment_amount_mismatch", user=payment.user,
                              metadata={"payment": payment.pk, "provider_amount": str(data.get("amount"))})
        except Exception:
            logger.exception("Could not record risk event")
        payment.refresh_from_db()
        return payment
    process_collection_callback({
        "externalId": str(payment.internal_reference),
        "status": data.get("status", ""),
        "transactionId": payment.provider_transaction_id or str(data.get("id") or ""),
    })
    payment.refresh_from_db()
    return payment


def reconcile_payment(payment: Payment) -> Payment:
    """Ask ioTec what happened and apply it. Sets ``payment.provider_check_failed = True`` when ioTec could not be
    reached or refused us (bad credentials, outage), so callers can tell "still waiting" from "we cannot check"."""
    payment.provider_check_failed = False
    if not is_recheckable(payment):
        return payment

    try:
        apply_collection_state(payment, fetch_collection_state(payment))
        if not is_recheckable(payment):
            return payment
    except IotecNotFound:
        if not payment.provider_transaction_id and _age_minutes(payment) > NOT_FOUND_GRACE_MINUTES:
            if fail_unsent_payment(payment):
                logger.warning("Payment %s never reached ioTec: closed as failed.", payment.pk)
                return payment
    except IotecPayError as exc:
        payment.provider_check_failed = True
        logger.warning("Reconciliation status check failed for payment=%s: %s", payment.pk, exc)

    if payment.status in OPEN_PAYMENT_STATUSES and _age_minutes(payment) > reconciliation_timeout_minutes():
        payment.status = Payment.Status.REQUIRES_REVIEW
        payment.save(update_fields=["status"])
        logger.warning("Payment %s flagged REQUIRES_REVIEW after reconciliation timeout.", payment.pk)

    return payment


def reconcile_all_pending_payments(report: list | None = None) -> dict:
    """Sweep every open payment (and recently parked ones). ``report``, if given, receives one dict per payment
    (id, before, after, check_failed) for the management command to print."""
    cutoff = timezone.now() - timedelta(days=REVIEW_RECHECK_DAYS)
    pending = Payment.objects.filter(
        Q(status__in=OPEN_PAYMENT_STATUSES) | Q(status=Payment.Status.REQUIRES_REVIEW, created_at__gte=cutoff))
    results = {"checked": 0, "resolved": 0, "flagged_for_review": 0}
    for payment in pending:
        before = payment.status
        reconcile_payment(payment)
        failed = getattr(payment, "provider_check_failed", False)
        payment.refresh_from_db()
        if report is not None:
            report.append({"id": payment.pk, "reference": str(payment.internal_reference), "before": before,
                           "after": payment.status, "check_failed": failed})
        results["checked"] += 1
        if payment.status in Payment.TERMINAL_STATUSES:
            results["resolved"] += 1
        elif payment.status == Payment.Status.REQUIRES_REVIEW:
            results["flagged_for_review"] += 1
    return results


def reconcile_withdrawal(withdrawal: Withdrawal) -> Withdrawal:
    open_states = (Withdrawal.Status.PENDING, Withdrawal.Status.PROCESSING)
    if withdrawal.status not in open_states:
        return withdrawal

    try:
        if withdrawal.provider_transaction_id:
            data = get_disbursement_status(withdrawal.provider_transaction_id)
        else:  # initiation response lost: look it up by our own reference
            data = get_disbursement_by_external_id(str(withdrawal.internal_reference))
        process_disbursement_callback({
            "externalId": str(withdrawal.internal_reference),
            "status": data.get("status", ""),
            "transactionId": withdrawal.provider_transaction_id or str(data.get("id") or ""),
        })
        withdrawal.refresh_from_db()
        if withdrawal.status not in open_states:
            return withdrawal
    except IotecNotFound:
        if not withdrawal.provider_transaction_id and _age_minutes(withdrawal) > NOT_FOUND_GRACE_MINUTES:
            if fail_unsent_withdrawal(withdrawal):
                logger.warning("Withdrawal %s never reached ioTec: closed as failed, balance released.", withdrawal.pk)
                return withdrawal
    except IotecPayError as exc:
        logger.warning("Reconciliation status check failed for withdrawal=%s: %s", withdrawal.pk, exc)

    if _age_minutes(withdrawal) > reconciliation_timeout_minutes():
        # Money may already be sent, so we never guess an outcome. Left as is; logged loudly for ops.
        logger.error("Withdrawal %s still open after reconciliation timeout: needs manual review.", withdrawal.pk)

    return withdrawal


def reconcile_all_pending_withdrawals() -> dict:
    pending = Withdrawal.objects.filter(status__in=[Withdrawal.Status.PENDING, Withdrawal.Status.PROCESSING])
    results = {"checked": 0, "resolved": 0}
    for withdrawal in pending:
        reconcile_withdrawal(withdrawal)
        withdrawal.refresh_from_db()
        results["checked"] += 1
        if withdrawal.status in Withdrawal.TERMINAL_STATUSES:
            results["resolved"] += 1
    return results


# ---------------------------------------------------------------------------
# Webhook entry points. A callback body is attacker-controllable, so it is
# only ever used to *locate* the record; the status that gets applied always
# comes from ioTec's own status API (same source the reconciliation job uses).
# ---------------------------------------------------------------------------

def _record_unverified(model_cb, payload, note):
    try:
        model_cb.objects.create(raw_payload=payload, provider_status=str(payload.get("status") or "").lower(),
                                provider_transaction_id=str(payload.get("transactionId") or ""), processed=False,
                                processing_notes=note)
    except Exception:  # never let bookkeeping break the webhook response
        logger.exception("Could not record unverified callback")


def verified_collection_callback(payload: dict):
    from ..models import PaymentCallback

    external_id = payload.get("externalId") or payload.get("external_id")
    payment = None
    if external_id:
        try:
            payment = Payment.objects.filter(internal_reference=external_id).first()
        except Exception:
            payment = None
    if payment is None:
        _record_unverified(PaymentCallback, payload, "No matching payment for externalId.")
        return None
    if payment.status in Payment.TERMINAL_STATUSES:
        return payment
    try:
        data = fetch_collection_state(payment)
    except IotecPayError as exc:
        logger.warning("Callback verification failed payment=%s: %s", payment.pk, exc)
        _record_unverified(PaymentCallback, payload, "Provider status unavailable; left for reconciliation.")
        return payment
    return apply_collection_state(payment, data)


def verified_disbursement_callback(payload: dict):
    from ..models import WithdrawalCallback

    external_id = payload.get("externalId") or payload.get("external_id")
    withdrawal = None
    if external_id:
        try:
            withdrawal = Withdrawal.objects.filter(internal_reference=external_id).first()
        except Exception:
            withdrawal = None
    if withdrawal is None:
        _record_unverified(WithdrawalCallback, payload, "No matching withdrawal for externalId.")
        return None
    tx_id = withdrawal.provider_transaction_id or str(payload.get("transactionId") or "")
    if not tx_id:
        _record_unverified(WithdrawalCallback, payload, "Cannot verify: no provider transaction id yet.")
        return withdrawal
    try:
        data = get_disbursement_status(tx_id)
    except IotecPayError as exc:
        logger.warning("Disbursement verification failed withdrawal=%s: %s", withdrawal.pk, exc)
        _record_unverified(WithdrawalCallback, payload, "Provider status unavailable; left for reconciliation.")
        return withdrawal
    return process_disbursement_callback({
        "externalId": str(withdrawal.internal_reference),
        "status": data.get("status", ""),
        "transactionId": tx_id,
    })
