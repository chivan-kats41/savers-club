from django.core.management.base import BaseCommand, CommandError

from accounts.models import User


class Command(BaseCommand):
    help = "Reset an admin's two-factor device (they must re-enrol on next login). Run on the server."

    def add_arguments(self, parser):
        parser.add_argument("phone")

    def handle(self, *args, **opts):
        user = User.objects.filter(phone=opts["phone"]).first()
        if user is None:
            raise CommandError("No such user.")
        user.totp_secret = ""
        user.totp_enabled = False
        user.save(update_fields=["totp_secret", "totp_enabled"])
        self.stdout.write(self.style.SUCCESS(f"2FA reset for {user.phone}."))
