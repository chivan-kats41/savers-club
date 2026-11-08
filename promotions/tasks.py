from celery import shared_task

from .services import expire_stale_promotions


@shared_task(name="promotions.expire_stale_promotions")
def expire_stale_promotions_task():
    return {"expired": expire_stale_promotions()}
