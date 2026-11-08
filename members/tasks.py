from celery import shared_task

from .services import credit_referral_rewards


@shared_task(name="members.credit_referral_rewards")
def credit_referral_rewards_task():
    return {"credited": credit_referral_rewards()}
