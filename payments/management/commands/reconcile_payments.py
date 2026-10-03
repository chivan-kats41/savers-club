from django.core.management.base import BaseCommand

from payments.services.reconciliation import reconcile_all_pending_payments, reconcile_all_pending_withdrawals


class Command(BaseCommand):
    help = "Reconciles PENDING payments and withdrawals against ioTec's status endpoints. Run on a schedule."

    def handle(self, *args, **options):
        payment_results = reconcile_all_pending_payments()
        self.stdout.write(self.style.SUCCESS(f"Payments: {payment_results}"))

        withdrawal_results = reconcile_all_pending_withdrawals()
        self.stdout.write(self.style.SUCCESS(f"Withdrawals: {withdrawal_results}"))
