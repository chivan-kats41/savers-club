from django.core.management.base import BaseCommand

from hub import data as d
from subscriptions.models import SubscriptionPlan

PERIOD_DAYS_BY_CODE = {
    "1K-MONTHLY": 30,
    "3K-QUARTERLY": 90,
    "6K-SEMI": 182,
    "10K-YEAR": 365,
}


class Command(BaseCommand):
    help = "Seeds SubscriptionPlan rows from hub/data.py's SUBSCRIPTION_PLANS (idempotent)."

    def handle(self, *args, **options):
        created = 0
        for row in d.SUBSCRIPTION_PLANS:
            period_days = PERIOD_DAYS_BY_CODE.get(row["code"], 30)
            _, was_created = SubscriptionPlan.objects.update_or_create(
                code=row["code"].lower(),
                defaults={
                    "label": row["label"],
                    "price": row["price"],
                    "period_days": period_days,
                    "is_popular": row.get("popular", False),
                    "is_active": True,
                },
            )
            created += was_created
        self.stdout.write(
            self.style.SUCCESS(
                f"Subscription plans: {created} created, {len(d.SUBSCRIPTION_PLANS) - created} already present."
            )
        )
