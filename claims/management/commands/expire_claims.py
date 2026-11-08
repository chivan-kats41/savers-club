from django.core.management.base import BaseCommand

from claims.services import expire_stale_claims


class Command(BaseCommand):
    help = "Expires CLAIMED claims past their expiry, restocking the offer for each. Run on a schedule."

    def handle(self, *args, **options):
        count = expire_stale_claims()
        self.stdout.write(self.style.SUCCESS(f"Expired {count} stale claim(s)."))
