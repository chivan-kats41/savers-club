"""SMS delivery through the ioTec Messaging API (https://messaging.iotec.io).

API reference (the OpenAPI spec supplied with the project):
  * Base URL ........ https://messaging-api.iotec.io
  * Auth ............ two headers on every request: ``Client-Id`` and ``X-Api-Key``
                      (both from the ioTec Messaging portal: Management > Settings > CONFIGURATION).
                      NOTE: these are *not* the ioTec Pay credentials (IOTEC_CLIENT_ID / IOTEC_CLIENT_SECRET).
  * Send ............ POST /api/sms-message   {"recipient": "0712345678", "body": "...", "referenceId": "..."}
  * Status .......... GET  /api/sms-message/{requestId}
  * Statuses ........ Pending, Processing, Sent, Failed, Scheduled, SentToVendor, SentForVerification, FailedDelivery

A 200 response means ioTec *accepted* the message; actual handset delivery is asynchronous
(use ``get_sms_status`` / the ``sms_status`` management command to follow up).

Configure with environment variables (see .env.example):
    SMS_GATEWAY_CLASS=notifications.services.sms_gateway.IoTecSMSGateway
    IOTEC_MESSAGING_CLIENT_ID=...
    IOTEC_MESSAGING_API_KEY=...
"""
import logging
import re
import uuid

import requests
from django.conf import settings
from django.utils.module_loading import import_string

logger = logging.getLogger("notifications")

MAX_BODY_CHARS = 480  # 3 concatenated SMS segments; longer messages are truncated, not rejected


class SMSTemporaryError(Exception):
    """The provider could not be reached or had a transient problem. Safe to retry."""


class SMSGateway:
    def send(self, phone: str, message: str) -> bool:
        raise NotImplementedError


class ConsoleSMSGateway(SMSGateway):
    """Development stub: logs instead of sending."""

    def send(self, phone: str, message: str) -> bool:
        logger.info("SMS (console) to %s: %s", phone, message)
        return True


# ---------------------------------------------------------------------------
# Phone numbers
# ---------------------------------------------------------------------------

def to_iotec_number(phone: str):
    """Normalise a Ugandan number and render it in the format ioTec expects.

    Accepts +2567XXXXXXXX, 2567XXXXXXXX, 07XXXXXXXX or 7XXXXXXXX. Anything else
    returns None so we never send an unvalidated string to the provider.
    Output style is controlled by IOTEC_MESSAGING_PHONE_FORMAT:
        local (default, matches the API docs' "0712345678"), international (256…), plus (+256…).
    """
    digits = re.sub(r"[\s\-().]", "", str(phone or ""))
    if digits.startswith("+"):
        digits = digits[1:]
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
    if national[0] != "7":  # Ugandan mobile numbers start with 7 (MTN/Airtel/etc.)
        return None
    style = getattr(settings, "IOTEC_MESSAGING_PHONE_FORMAT", "local")
    if style == "international":
        return "256" + national
    if style == "plus":
        return "+256" + national
    return "0" + national


def mask_phone(phone: str) -> str:
    p = str(phone or "")
    return p[:4] + "•" * max(len(p) - 7, 0) + p[-3:] if len(p) > 7 else "•••"


# ---------------------------------------------------------------------------
# ioTec Messaging
# ---------------------------------------------------------------------------

def _credentials():
    client_id = getattr(settings, "IOTEC_MESSAGING_CLIENT_ID", "")
    api_key = getattr(settings, "IOTEC_MESSAGING_API_KEY", "")
    return client_id, api_key


def _headers(client_id, api_key):
    return {"Client-Id": client_id, "X-Api-Key": api_key, "Accept": "application/json"}


def _base_url():
    return getattr(settings, "IOTEC_MESSAGING_BASE_URL", "https://messaging-api.iotec.io").rstrip("/")


def _timeout():
    return getattr(settings, "IOTEC_MESSAGING_TIMEOUT", 10)


FAILED_STATUSES = {"failed", "faileddelivery"}


class IoTecSMSGateway(SMSGateway):
    def send(self, phone: str, message: str) -> bool:
        client_id, api_key = _credentials()
        if not client_id or not api_key:
            logger.error("ioTec Messaging credentials are not configured (IOTEC_MESSAGING_CLIENT_ID / _API_KEY); SMS not sent.")
            return False
        recipient = to_iotec_number(phone)
        if recipient is None:
            logger.warning("Refusing to send SMS: %s is not a valid Ugandan mobile number.", mask_phone(phone))
            return False
        body = (message or "").strip()[:MAX_BODY_CHARS]
        if not body:
            return False

        reference = f"1k-{uuid.uuid4().hex[:16]}"
        try:
            resp = requests.post(
                f"{_base_url()}/api/sms-message",
                json={"recipient": recipient, "body": body, "referenceId": reference},
                headers=_headers(client_id, api_key),
                timeout=_timeout(),
            )
        except (requests.Timeout, requests.ConnectionError) as exc:
            raise SMSTemporaryError(f"ioTec Messaging unreachable: {type(exc).__name__}") from exc

        if resp.status_code in (401, 403):
            # Wrong or revoked credentials: retrying will not help; make it loud.
            logger.error("ioTec Messaging rejected our credentials (HTTP %s). Regenerate the API key in the portal.", resp.status_code)
            return False
        if resp.status_code == 429 or resp.status_code >= 500:
            raise SMSTemporaryError(f"ioTec Messaging temporary error HTTP {resp.status_code}")
        if resp.status_code != 200:
            logger.warning("ioTec Messaging refused SMS to %s (HTTP %s).", mask_phone(phone), resp.status_code)
            return False

        try:
            data = resp.json()
        except ValueError:
            logger.warning("ioTec Messaging returned a non-JSON 200 for %s.", mask_phone(phone))
            return False
        status = str(data.get("status", "")).lower()
        if status in FAILED_STATUSES:
            logger.warning("ioTec Messaging could not queue SMS to %s: %s (%s)", mask_phone(phone),
                           data.get("errorMessage") or data.get("statusMessage") or status, data.get("errorCode"))
            return False
        logger.info("SMS accepted by ioTec id=%s ref=%s status=%s to=%s", data.get("id"), reference, data.get("status"), mask_phone(phone))
        return True


def get_sms_status(request_id: str) -> dict:
    """GET /api/sms-message/{requestId}. Returns the provider's JSON (id, status, statusMessage, errorMessage…)."""
    client_id, api_key = _credentials()
    if not client_id or not api_key:
        raise SMSTemporaryError("ioTec Messaging credentials are not configured.")
    try:
        uuid.UUID(str(request_id))
    except ValueError:
        raise ValueError("request_id must be a UUID")
    resp = requests.get(f"{_base_url()}/api/sms-message/{request_id}", headers=_headers(client_id, api_key), timeout=_timeout())
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def get_sms_gateway() -> SMSGateway:
    return import_string(settings.SMS_GATEWAY_CLASS)()


def send_sms(phone: str, message: str, raise_transient: bool = False) -> bool:
    """Send one SMS. Returns True when the provider accepted it.

    With ``raise_transient=True`` a temporary provider problem raises
    ``SMSTemporaryError`` (so a Celery task can retry); otherwise it returns False.
    """
    if not phone:
        return False
    try:
        return get_sms_gateway().send(phone, message)
    except SMSTemporaryError:
        if raise_transient:
            raise
        logger.warning("SMS to %s failed (temporary provider problem).", mask_phone(phone))
        return False
    except Exception:
        logger.exception("SMS send failed for %s", mask_phone(phone))
        return False
