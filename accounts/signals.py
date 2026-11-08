from django.conf import settings
from django.contrib.auth.signals import user_logged_in
from django.db.models.signals import post_save
from django.dispatch import receiver

from .admin_profiles import ensure_admin_profiles, is_super_admin
from .models import User

# Fields whose change can turn someone into a super admin. A plain `last_login` save must not trigger the work.
RELEVANT = {"is_superuser", "role"}


@receiver(post_save, sender=User)
def create_profiles_for_super_admin(sender, instance, created, update_fields=None, **kwargs):
    """`createsuperuser`, the Django admin, a shell, or a role change: whenever someone is (or becomes) a super admin."""
    if not getattr(settings, "AUTO_CREATE_ADMIN_PROFILES", True):
        return
    if update_fields and not (RELEVANT & set(update_fields)):
        return
    if is_super_admin(instance):
        ensure_admin_profiles(instance)


@receiver(user_logged_in)
def heal_profiles_on_login(sender, request, user, **kwargs):
    """Existing super admins (created before this feature) get their profiles on next login, and areas / categories
    added since then are picked up."""
    if getattr(settings, "AUTO_CREATE_ADMIN_PROFILES", True) and is_super_admin(user):
        ensure_admin_profiles(user)
