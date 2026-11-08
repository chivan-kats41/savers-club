from django.core.management.base import BaseCommand

from members.services import credit_referral_rewards


class Command(BaseCommand):
    help = "Credit referral rewards whose hold period has passed, making them withdrawable."

    def handle(self, *args, **options):
        self.stdout.write(f"Credited {credit_referral_rewards()} referral reward(s).")
