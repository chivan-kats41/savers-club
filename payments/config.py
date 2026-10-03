"""One place that answers "how is ioTec Pay configured right now?".

The flat IOTEC_* settings are the source of truth (so tests/overrides work);
`PAYMENT_PROVIDERS["IOTECH_PAY"]` in settings mirrors them in the shape many
Django projects use. Read through here, never straight from settings.
"""
import re

from django.conf import settings

VALID_CURRENCIES = {"UGX", "USD", "ITX"}
VALID_CHARGES = {"", "ChargeCustomer", "ChargeWallet"}
MIN_AMOUNT = 500  # ioTec rejects collections/disbursements below UGX 500


def currency() -> str:
    cur = str(getattr(settings, "IOTEC_CURRENCY", "UGX") or "UGX").upper()
    return cur if cur in VALID_CURRENCIES else "UGX"


def charges_category() -> str:
    cat = getattr(settings, "IOTEC_CHARGES_CATEGORY", "") or ""
    return cat if cat in VALID_CHARGES else ""


def is_configured() -> bool:
    return bool(settings.IOTEC_CLIENT_ID and settings.IOTEC_CLIENT_SECRET and settings.IOTEC_WALLET_ID)


def return_url(payment_ref) -> str:
    """Absolute https URL ioTec sends the cardholder back to. Empty (=> ioTec shows its own
    confirmation page) unless SITE_URL is a real https address: the API rejects non-https."""
    base = (getattr(settings, "SITE_URL", "") or "").rstrip("/")
    if not base.startswith("https://"):
        return ""
    return f"{base}/payments/return/?ref={payment_ref}"


# ---- phone / email normalisation -------------------------------------------------------------

def normalize_msisdn(raw: str):
    """+2567XXXXXXXX / 07XXXXXXXX / 7XXXXXXXX -> 2567XXXXXXXX, or None if it isn't a Ugandan mobile."""
    digits = re.sub(r"[\s\-().]", "", str(raw or "")).lstrip("+")
    if not digits.isdigit():
        return None
    if digits.startswith("256") and len(digits) == 12:
        national = digits[3:]
    elif digits.startswith("0") and len(digits) == 10:
        national = digits[1:]
    elif len(digits) == 9:
        national = digits
    else:
        return None
    return "256" + national if national[0] == "7" else None


_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")


def valid_email(raw: str) -> bool:
    return bool(_EMAIL.match(str(raw or "").strip())) and len(str(raw)) <= 254


def note(text: str, limit: int = 100) -> str:
    return str(text or "")[:limit]
