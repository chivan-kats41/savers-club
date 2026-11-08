from django.conf import settings
from django.core.management.base import BaseCommand

from payments import config
from payments.services.iotec_auth import IotecAuthError, get_access_token
from payments.services.iotec_client import IotecPayError
from payments.services.iotec_disbursements import get_wallet_balance


class Command(BaseCommand):
    help = ("Verify the ioTec Pay setup WITHOUT moving any money: credentials (token), wallet id (balance), "
            "callback URL/secret, card return URL. Secrets are never printed.")

    def handle(self, *args, **opts):
        problems = 0

        def ok(msg): self.stdout.write(self.style.SUCCESS("  OK   ") + msg)
        def warn(msg): self.stdout.write(self.style.WARNING("  WARN ") + msg)
        def bad(msg):
            nonlocal problems
            problems += 1
            self.stdout.write(self.style.ERROR("  FAIL ") + msg)

        self.stdout.write("ioTec Pay configuration")
        self.stdout.write(f"  Base URL: {settings.IOTEC_BASE_URL}   Currency: {config.currency()}")
        for name, val in (("IOTEC_API_KEY", settings.IOTEC_CLIENT_ID), ("IOTEC_SECRET_KEY", settings.IOTEC_CLIENT_SECRET),
                          ("IOTEC_WALLET_ID", settings.IOTEC_WALLET_ID)):
            (ok if val else bad)(f"{name} is {'set' if val else 'MISSING'}")
        if problems:
            self.stdout.write(self.style.ERROR("Fix the missing values in .env, then run this again."))
            return

        try:
            get_access_token(force_refresh=True)
            ok("Credentials accepted by ioTec (token issued)")
        except IotecAuthError as exc:
            bad(f"ioTec refused the API key / secret: {exc}")
            return

        try:
            wallet = get_wallet_balance()
            ok(f"Wallet found: {wallet.get('name') or '(unnamed)'} - balance "
               f"{wallet.get('currency', config.currency())} {wallet.get('actualBalance')}")
            if str(wallet.get("currency", config.currency())).upper() != config.currency():
                warn(f"Wallet currency is {wallet.get('currency')} but IOTEC_CURRENCY is {config.currency()}")
        except IotecPayError as exc:
            bad(f"Could not read the wallet (wrong IOTEC_WALLET_ID, or this key can't access it?): {exc}")

        cb = settings.IOTECH_CALLBACK_URL
        if not cb:
            warn("IOTECH_CALLBACK_URL is not set. Payments still complete (we poll ioTec), just a little slower.")
        else:
            (ok if cb.startswith("https://") else warn)(f"Callback URL to register in the ioTec portal: {cb}")
            if not cb.rstrip("/").endswith("/api/iotec/callback"):
                warn("That URL does not end in /api/iotec/callback, which is where this project listens.")
        if not settings.IOTEC_CALLBACK_SECRET:
            (warn if settings.DEBUG else bad)("IOTEC_CALLBACK_SECRET is empty: callbacks are rejected outside DEBUG.")
        else:
            ok("IOTEC_CALLBACK_SECRET is set (send it from ioTec as X-Callback-Secret or Authorization: Bearer)")
        if not settings.SITE_URL.startswith("https://"):
            warn("SITE_URL is not an https address: card payers will see ioTec's generic page instead of coming "
                 "back to your site (their payment still completes).")
        else:
            ok(f"Card return page: {settings.SITE_URL}/payments/return/")

        self.stdout.write(self.style.ERROR(f"{problems} problem(s) found.") if problems else self.style.SUCCESS("All checks passed."))
