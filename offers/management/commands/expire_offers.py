from django.core.management.base import BaseCommand

from offers.services import expire_stale_offers


class Command(BaseCommand):
    help = "Marks ACTIVE offers past their expires_at as EXPIRED. Run on a schedule."

    def handle(self, *args, **options):
        count = expire_stale_offers()
        self.stdout.write(self.style.SUCCESS(f"Expired {count} stale offer(s)."))
