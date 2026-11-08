from django.core.management.base import BaseCommand

from geo.services.history import purge_expired


class Command(BaseCommand):
    help = "Delete location history past its retention period (and stale last-known positions). Idempotent."

    def handle(self, *args, **options):
        r = purge_expired()
        self.stdout.write(self.style.SUCCESS(
            f"Purged {r['history']} history rows, {r['rider_live']} rider live rows, {r['stale_fixes']} stale positions."))
