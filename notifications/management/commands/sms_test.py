from django.core.management.base import BaseCommand, CommandError

from notifications.services.sms_gateway import SMSTemporaryError, get_sms_gateway, mask_phone, to_iotec_number


class Command(BaseCommand):
    help = "Send a test SMS through the configured gateway (use this to verify ioTec Messaging credentials)."

    def add_arguments(self, parser):
        parser.add_argument("phone", help="e.g. +256700000000 or 0700000000")
        parser.add_argument("--message", default="1K Saver Club test message. SMS is working.")

    def handle(self, *args, **opts):
        phone = opts["phone"]
        gateway = get_sms_gateway()
        self.stdout.write(f"Gateway: {type(gateway).__module__}.{type(gateway).__name__}")
        self.stdout.write(f"Recipient as sent to provider: {to_iotec_number(phone) or 'INVALID NUMBER'} ({mask_phone(phone)})")
        try:
            ok = gateway.send(phone, opts["message"])
        except SMSTemporaryError as exc:
            raise CommandError(f"Provider unreachable / temporary error: {exc}")
        if not ok:
            raise CommandError("The provider did not accept the message. See the logs above (credentials? number format?).")
        self.stdout.write(self.style.SUCCESS("Accepted by the provider. Delivery to the handset is asynchronous."))
