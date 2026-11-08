"""Step-up confirmation for taking money OUT.

A stolen or left-open session must not be enough to send someone's earnings to a stranger's number: every withdrawal
needs a one-time code texted to the number ON THE ACCOUNT (never the payout number the request names). The code is
hashed at rest, expires in 10 minutes, allows 5 guesses, at most 3 are issued per hour, and is consumed only when the
withdrawal is actually created (a request rejected for, say, low balance does not burn it).
"""
from __future__ import annotations

import logging

from django.conf import settings

from accounts.models import PhoneVerification
from core.services import get_setting

logger = logging.getLogger("security")


def code_required() -> bool:
    return str(get_setting("withdrawal.require_code", "1")).strip().lower() not in ("0", "false", "no", "off")


def issue_code(user):
    """Create a withdrawal code and SMS it to the account's phone. Returns (sms_accepted, dev_code_or_None).
    Raises accounts.models.OTPRateLimited when too many were requested this hour."""
    from notifications.services.sms_gateway import send_sms

    _, raw = PhoneVerification.issue(user, PhoneVerification.Purpose.WITHDRAWAL)
    text = (f"1K Saver Club: {raw} is your code to confirm your withdrawal. It expires in 10 minutes. "
            "If you did not ask for it, do not share it: someone may be trying to use your account.")
    sent = send_sms(user.phone, text)
    logger.info("Withdrawal code issued user=%s sms_accepted=%s", user.id, sent)
    return sent, (raw if settings.DEBUG else None)


def check_code(user, raw_code):
    """The matching, still-valid PhoneVerification (NOT yet consumed) or None."""
    raw = str(raw_code or "").strip()
    if not raw:
        return None
    verification = (PhoneVerification.objects
                    .filter(user=user, purpose=PhoneVerification.Purpose.WITHDRAWAL, is_used=False)
                    .order_by("-created_at").first())
    if verification is None or not verification.check_code(raw):
        return None
    return verification
