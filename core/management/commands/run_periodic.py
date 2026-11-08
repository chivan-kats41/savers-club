"""Runs the scheduled housekeeping jobs without Celery beat, for hosts like PythonAnywhere.

    python manage.py run_periodic          # loop forever (use as an Always-on task)
    python manage.py run_periodic --once   # run every job once and exit (use as an hourly Scheduled task)

Every job is idempotent, so running one twice is harmless.
"""
import logging
import time

from django.core.management import call_command
from django.core.management.base import BaseCommand

logger = logging.getLogger("payments")

# (command, seconds between runs). Mirrors config/celery.py's beat schedule.
JOBS = [
    ("reconcile_payments", 300),        # settle pending payments / withdrawals against ioTec
    ("expire_claims", 600),
    ("expire_deliveries", 600),         # cancel online-pay delivery requests nobody paid
    ("expire_offers", 3600),
    ("expire_subscriptions", 3600),
    ("expire_promotions", 3600),
    ("credit_referral_rewards", 3600),  # release referral rewards after the hold period
    ("purge_location_history", 6 * 3600),   # delete location trails past their retention
    ("send_nearby_deal_alerts", 3600),      # opt-in "hot deal near you" push alerts (quiet hours respected)
]


class Command(BaseCommand):
    help = "Run the periodic housekeeping jobs (payment reconciliation, expiries, referral credits) without Celery."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Run every job once and exit.")

    def _run(self, name):
        try:
            call_command(name)
        except Exception:  # one failing job must never stop the others
            logger.exception("Periodic job %s failed", name)

    def handle(self, *args, **options):
        if options["once"]:
            for name, _ in JOBS:
                self._run(name)
            return

        last_run = {name: 0.0 for name, _ in JOBS}
        self.stdout.write("run_periodic started; press Ctrl+C to stop.")
        while True:
            now = time.monotonic()
            for name, every in JOBS:
                if now - last_run[name] >= every:
                    last_run[name] = now
                    self._run(name)
            time.sleep(30)
