from django.core.management.base import BaseCommand

from payments.services.reconciliation import reconcile_all_pending_payments, reconcile_all_pending_withdrawals


class Command(BaseCommand):
    help = "Reconciles PENDING payments and withdrawals against ioTec's status endpoints. Run on a schedule."

    def handle(self, *args, **options):
        report = []
        payment_results = reconcile_all_pending_payments(report)
        for row in report:
            line = f"  payment #{row['id']} ({row['reference'][:8]}…): {row['before']} -> {row['after']}"
            if row["check_failed"]:
                line += "   [could not reach/authenticate with ioTec: check IOTEC_* settings and payments.log]"
            self.stdout.write(line)
        self.stdout.write(self.style.SUCCESS(f"Payments: {payment_results}"))

        withdrawal_results = reconcile_all_pending_withdrawals()
        self.stdout.write(self.style.SUCCESS(f"Withdrawals: {withdrawal_results}"))
