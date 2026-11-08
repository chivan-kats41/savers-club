from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from subscriptions.models import SubscriptionPayment
from subscriptions.services import confirm_payment


class Command(BaseCommand):
    help = (
        "DEV ONLY: manually confirms a pending SubscriptionPayment as "
        "success or failed, exercising the same code path a real ioTec "
        "callback will use once the payments app exists (Phase 7). "
        "Refuses to run outside DEBUG."
    )

    def add_arguments(self, parser):
        parser.add_argument("external_reference", type=str)
        parser.add_argument("--fail", action="store_true", help="Simulate a failed payment instead of success.")

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("This command only runs with DEBUG=True.")

        try:
            payment = SubscriptionPayment.objects.get(external_reference=options["external_reference"])
        except SubscriptionPayment.DoesNotExist as exc:
            raise CommandError("No payment with that external_reference.") from exc

        subscription = confirm_payment(payment, success=not options["fail"])
        payment.refresh_from_db()
        self.stdout.write(
            self.style.SUCCESS(
                f"Payment {payment.pk} -> {payment.status}. Subscription now {subscription.status} "
                f"(period ends {subscription.current_period_end})."
            )
        )
