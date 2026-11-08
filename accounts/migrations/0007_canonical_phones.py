"""Rewrite existing phone numbers to the canonical +2567XXXXXXXX spelling.

Safe by construction: a number is only rewritten when exactly ONE account owns that SIM (under any spelling) and its
current spelling differs. If two accounts hold the same number written differently (the duplicate-account problem this
release stops), neither is touched: a person has to decide which one is real. Login accepts every spelling either way.
"""
import re

from django.db import migrations

_STRIP = re.compile(r"[\s\-().]")


def _canonical(raw):
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


def canonicalise(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    groups = {}
    for pk, phone in User.objects.values_list("pk", "phone"):
        canon = _canonical(phone)
        if canon:
            groups.setdefault(canon, []).append((pk, phone))
    for canon, owners in groups.items():
        if len(owners) == 1 and owners[0][1] != canon:
            User.objects.filter(pk=owners[0][0]).update(phone=canon)


class Migration(migrations.Migration):
    dependencies = [("accounts", "0006_withdrawal_otp_and_ip_index")]
    operations = [migrations.RunPython(canonicalise, migrations.RunPython.noop)]
