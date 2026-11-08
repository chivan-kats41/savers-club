from celery import shared_task

from .services import expire_unpaid_deliveries


@shared_task(name="deliveries.expire_unpaid_deliveries")
def expire_unpaid_deliveries_task():
    return {"cancelled": expire_unpaid_deliveries()}
