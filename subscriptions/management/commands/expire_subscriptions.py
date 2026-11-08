from django.core.management.base import BaseCommand

from subscriptions.services import expire_stale_subscriptions


class Command(BaseCommand):
    help = "Marks ACTIVE subscriptions past their current_period_end as EXPIRED. Run on a schedule."

    def handle(self, *args, **options):
        count = expire_stale_subscriptions()
        self.stdout.write(self.style.SUCCESS(f"Expired {count} stale subscription(s)."))
