from django.core.management.base import BaseCommand

from promotions.services import expire_stale_promotions


class Command(BaseCommand):
    help = "Marks ACTIVE promotions past their expires_at as EXPIRED, reverting the visibility boost. Run on a schedule."

    def handle(self, *args, **options):
        count = expire_stale_promotions()
        self.stdout.write(self.style.SUCCESS(f"Expired {count} stale promotion(s)."))
