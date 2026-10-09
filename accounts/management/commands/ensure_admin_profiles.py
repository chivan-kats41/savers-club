from django.core.management.base import BaseCommand
from django.db.models import Q

from accounts.admin_profiles import ensure_admin_profiles
from accounts.models import Role, User


class Command(BaseCommand):
    help = ("Create the member, merchant, rider and agent profiles for every super admin (or one user). "
            "Idempotent: existing profiles are left untouched. New super admins get this automatically.")

    def add_arguments(self, parser):
        parser.add_argument("phone", nargs="?", help="Only this user (must be a super admin). Default: all super admins.")

    def handle(self, *args, **opts):
        users = User.objects.filter(Q(is_superuser=True) | Q(role=Role.SUPER_ADMIN))
        if opts["phone"]:
            users = users.filter(phone=opts["phone"])
        if not users.exists():
            self.stdout.write(self.style.WARNING("No matching super admin found."))
            return
        for user in users:
            r = ensure_admin_profiles(user)
            have = ", ".join(sorted(r.present)) or "none"
            self.stdout.write(f"{user.phone}: has [{have}]; created {r.created or 'nothing'}"
                              + (f"; added {r.areas_added} area(s) to agent" if r.areas_added else ""))
            for profile, why in r.skipped.items():
                self.stdout.write(self.style.WARNING(f"   could not create {profile}: {why}"))
