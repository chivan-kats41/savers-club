from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand

from accounts.models import Role, User

DEFAULT_ADMIN_CAPABILITIES = [
    "payments_view", "withdrawals_approve", "users_suspend",
    "merchant_verify", "rider_verify", "agent_manage", "reports_view",
    "offers_moderate", "notifications_broadcast", "content_manage",
]
# Deliberately excluded from the default group — these are the most
# sensitive operations and should be granted individually, or reserved
# for SUPER_ADMIN (who bypasses capability checks entirely via
# is_superuser=True): payments_refund, payments_settle,
# withdrawals_reverse, fees_manage, settings_manage.


class Command(BaseCommand):
    help = "Creates the 'Platform Admin' group with a starter capability set and assigns role=admin users to it."

    def handle(self, *args, **options):
        group, _ = Group.objects.get_or_create(name="Platform Admin")

        perms = Permission.objects.filter(content_type__app_label="core", codename__in=DEFAULT_ADMIN_CAPABILITIES)
        group.permissions.set(perms)
        self.stdout.write(self.style.SUCCESS(f"'Platform Admin' group has {perms.count()} capabilities."))

        admins = User.objects.filter(role=Role.ADMIN)
        for user in admins:
            user.groups.add(group)
        self.stdout.write(self.style.SUCCESS(f"Assigned {admins.count()} admin-role user(s) to the group."))
