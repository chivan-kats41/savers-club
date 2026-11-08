import json

from django.core.management.base import BaseCommand, CommandError

from notifications.services.sms_gateway import get_sms_status


class Command(BaseCommand):
    help = "Look up an SMS by the id ioTec returned (see the 'SMS accepted by ioTec id=…' log line)."

    def add_arguments(self, parser):
        parser.add_argument("request_id")

    def handle(self, *args, **opts):
        try:
            data = get_sms_status(opts["request_id"])
        except Exception as exc:
            raise CommandError(str(exc))
        self.stdout.write(json.dumps(data, indent=2, default=str))
