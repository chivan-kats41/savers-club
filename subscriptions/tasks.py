from celery import shared_task

from .services import expire_stale_subscriptions


@shared_task(name="subscriptions.expire_stale_subscriptions")
def expire_stale_subscriptions_task():
    return {"expired": expire_stale_subscriptions()}
