from django.core.management.base import BaseCommand

from geo.services.alerts import send_nearby_deal_alerts


class Command(BaseCommand):
    help = "Send opt-in 'hot deal near you' alerts (in-app + push; max one a day; quiet hours respected). Idempotent."

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS(f"Sent {send_nearby_deal_alerts()} alert(s)."))
