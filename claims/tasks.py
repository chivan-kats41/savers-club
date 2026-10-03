from celery import shared_task

from .services import expire_stale_claims


@shared_task(name="claims.expire_stale_claims")
def expire_stale_claims_task():
    return {"expired": expire_stale_claims()}
