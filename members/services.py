from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from core.services import get_setting_int

from .models import ReferralReward


@transaction.atomic
def credit_referral_rewards() -> int:
    """Turn PENDING referral rewards into CREDITED (withdrawable) once the hold period has passed.

    A reward is created when the referred friend's first subscription payment succeeds. Holding it for
    `referral.hold_days` (default 7) before it becomes withdrawable guards against refunds / chargebacks and
    quick sign-up farming. Safe to run repeatedly (cron / Celery beat / PythonAnywhere scheduled task)."""
    hold_days = get_setting_int("referral.hold_days", 7)
    cutoff = timezone.now() - timedelta(days=hold_days)
    now = timezone.now()
    credited = 0
    for reward in ReferralReward.objects.select_for_update().filter(status=ReferralReward.Status.PENDING, created_at__lte=cutoff):
        reward.status = ReferralReward.Status.CREDITED
        reward.credited_at = now
        reward.save(update_fields=["status", "credited_at"])
        credited += 1
    return credited
