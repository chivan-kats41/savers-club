from celery import shared_task

from .services import expire_stale_offers


@shared_task(name="offers.expire_stale_offers")
def expire_stale_offers_task():
    return {"expired": expire_stale_offers()}
