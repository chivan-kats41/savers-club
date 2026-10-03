import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

app = Celery("savings_hub")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

app.conf.beat_schedule = {
    "reconcile-pending-payments": {
        "task": "payments.reconcile_pending_payments",
        "schedule": crontab(minute="*/5"),
    },
    "reconcile-pending-withdrawals": {
        "task": "payments.reconcile_pending_withdrawals",
        "schedule": crontab(minute="*/5"),
    },
    "expire-stale-claims": {
        "task": "claims.expire_stale_claims",
        "schedule": crontab(minute="*/10"),
    },
    "expire-stale-offers": {
        "task": "offers.expire_stale_offers",
        "schedule": crontab(minute=0),
    },
    "expire-stale-subscriptions": {
        "task": "subscriptions.expire_stale_subscriptions",
        "schedule": crontab(minute=0),
    },
    "expire-stale-promotions": {
        "task": "promotions.expire_stale_promotions",
        "schedule": crontab(minute=0),
    },
}
