from decimal import Decimal

from django.conf import settings

from payments import config
from payments.models import Payment

from .iotec_client import IotecPayClient, IotecPayError


def _amount(payment: Payment) -> float:
    amount = Decimal(payment.amount)
    if amount < config.MIN_AMOUNT:
        raise IotecPayError(f"The minimum payment is {config.currency()} {config.MIN_AMOUNT}.")
    return float(amount)


def _common(payment: Payment, category: str) -> dict:
    body = {
        "category": category,
        "currency": config.currency(),
        "walletId": settings.IOTEC_WALLET_ID,
        "externalId": str(payment.internal_reference),
        "amount": _amount(payment),                       # required by the API (min 500)
        "payerNote": config.note(f"1K Saver Club {payment.get_purpose_display()}"),
        "payeeNote": config.note(f"Payment {payment.internal_reference}"),
    }
    if config.charges_category():
        body["transactionChargesCategory"] = config.charges_category()
    return body


def initiate_mobile_money_collection(payment: Payment) -> dict:
    """POST /api/collections/collect — sends a prompt to the payer's phone (MTN or Airtel; ioTec works out
    the network from the number). The payment stays Pending until the payer approves/declines or it times
    out. We never mark a Payment successful here: only a provider-verified status does that."""
    payer = config.normalize_msisdn(payment.payer_phone)
    if payer is None:
        raise IotecPayError("Enter a valid MTN or Airtel number, e.g. 0772 123 456.")
    body = _common(payment, "MobileMoney")
    body["payer"] = payer
    body["payerName"] = config.note(payment.user.get_full_name() if payment.user_id else "", 150)
    data = IotecPayClient().post("/api/collections/collect", body)

    payment.provider_transaction_id = data.get("id") or data.get("transactionId") or ""
    payment.status = Payment.Status.PENDING
    payment.save(update_fields=["provider_transaction_id", "status"])
    return data


def initiate_card_collection(payment: Payment) -> dict:
    """POST /api/collections/collect/card — Visa/MasterCard through ioTec's hosted PegPay page.

    1. We get back a Pending transaction with `cardRedirectUrl`.
    2. We send the customer's browser there; they enter card details on PegPay (never on our site, so we
       never see or store card data).
    3. PegPay returns them to `redirectUrl` (our /payments/return/ page, https only). That page does NOT
       trust the query string: it asks ioTec for the real status."""
    if not config.valid_email(payment.payer_email):
        raise IotecPayError("A valid email address is required for card payments.")
    body = _common(payment, "Card")
    body["payer"] = payment.payer_email.strip()
    body["payerName"] = config.note(payment.user.get_full_name() if payment.user_id else "", 150)
    return_url = config.return_url(payment.internal_reference)
    if return_url:
        body["redirectUrl"] = return_url
    data = IotecPayClient().post("/api/collections/collect/card", body)

    redirect = data.get("cardRedirectUrl", "") or ""
    if not redirect:
        raise IotecPayError("ioTec did not return a card payment page. Please try again or use mobile money.")
    payment.provider_transaction_id = data.get("id") or data.get("transactionId") or ""
    payment.redirect_url = redirect
    payment.status = Payment.Status.PENDING
    payment.save(update_fields=["provider_transaction_id", "redirect_url", "status"])
    return data


def get_collection_status(request_id: str) -> dict:
    """GET /api/collections/status/{requestId}"""
    return IotecPayClient().get(f"/api/collections/status/{request_id}")


def get_collection_by_external_id(external_id: str) -> dict:
    """GET /api/collections/external-id/{externalId}"""
    return IotecPayClient().get(f"/api/collections/external-id/{external_id}")
