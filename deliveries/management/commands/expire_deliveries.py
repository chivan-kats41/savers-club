from django.core.management.base import BaseCommand

from deliveries.services import expire_unpaid_deliveries


class Command(BaseCommand):
    help = "Cancel online-pay delivery requests whose customer never completed payment (frees the claim to request again)."

    def handle(self, *args, **options):
        self.stdout.write(f"Cancelled {expire_unpaid_deliveries()} unpaid delivery request(s).")
