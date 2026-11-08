"""Disbursements (money out to a rider's mobile money).

Request fields below are taken from the ioTec Pay v1 OpenAPI spec (DisbursementRequest):
required `amount` (number, min 500) and `payee`; plus category, currency, walletId, externalId,
payeeName, payerNote, payeeNote.
"""
from decimal import Decimal

from django.conf import settings

from payments import config
from payments.models import Withdrawal

from .iotec_client import IotecPayClient, IotecPayError


def initiate_disbursement(withdrawal: Withdrawal) -> dict:
    payee = config.normalize_msisdn(withdrawal.phone)
    if payee is None:
        raise IotecPayError("The withdrawal phone number is not a valid MTN/Airtel number.")
    amount = Decimal(withdrawal.net_amount)
    if amount < config.MIN_AMOUNT:
        raise IotecPayError(f"The amount to send must be at least {config.currency()} {config.MIN_AMOUNT}.")
    body = {
        "category": "MobileMoney",
        "currency": config.currency(),
        "walletId": settings.IOTEC_WALLET_ID,
        "externalId": str(withdrawal.internal_reference),
        "payee": payee,
        "payeeName": config.note(withdrawal.user.get_full_name() if withdrawal.user_id else "", 150),
        "amount": float(amount),
        "payerNote": config.note("1K Saver Club withdrawal"),
        "payeeNote": config.note(f"Withdrawal {withdrawal.internal_reference}"),
    }
    data = IotecPayClient().post("/api/disbursements/disburse", body)

    withdrawal.provider_transaction_id = data.get("id") or data.get("transactionId") or ""
    withdrawal.status = Withdrawal.Status.PROCESSING
    withdrawal.save(update_fields=["provider_transaction_id", "status"])
    return data


def get_disbursement_status(transaction_id: str) -> dict:
    return IotecPayClient().get(f"/api/disbursements/status/{transaction_id}")


def get_disbursement_by_external_id(external_id: str) -> dict:
    return IotecPayClient().get(f"/api/disbursements/external-id/{external_id}")


def get_bank_list() -> dict:
    return IotecPayClient().get("/api/disbursements/bank-list")


def get_wallet_balance() -> dict:
    """GET /api/wallet-balance/{walletId} -> {name, currency, actualBalance, ...}"""
    return IotecPayClient().get(f"/api/wallet-balance/{settings.IOTEC_WALLET_ID}")
