"""One canonical spelling for Ugandan mobile numbers, and for the "phone or email" a person types at login.

Without this, 0772123456, +256772123456, 772123456 and "0772 123 456" were four different accounts for one SIM, and
each spelling (or each letter-case of an email) had its own failed-login counter. Canonical phone: +2567XXXXXXXX.
"""
from __future__ import annotations

import re

_STRIP = re.compile(r"[\s\-().]")


def canonical_phone(raw) -> str | None:
    """'+2567XXXXXXXX' for any accepted spelling of a Ugandan mobile number, else None."""
    digits = _STRIP.sub("", str(raw or "")).lstrip("+")
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
    return "+256" + national if national[0] == "7" else None


def phone_variants(raw) -> list[str]:
    """Every spelling a legacy row might have been stored with (canonical first). [] if not a Ugandan mobile."""
    canon = canonical_phone(raw)
    if canon is None:
        return []
    national = canon[4:]
    return [canon, "256" + national, "0" + national, national]


def canonical_identifier(raw) -> str:
    """What a login attempt is counted against: the canonical phone, or the lower-cased email, so that changing the
    spelling or letter-case does not buy a fresh set of guesses."""
    text = str(raw or "").strip()
    phone = canonical_phone(text)
    if phone:
        return phone
    return text.lower()
