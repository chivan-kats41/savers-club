from rest_framework.permissions import BasePermission, SAFE_METHODS

from .models import ADMIN_ROLES


class IsRole(BasePermission):
    """Usage: permission_classes = [IsRole.for_roles('member', 'agent')]"""

    roles = ()

    @classmethod
    def for_roles(cls, *roles):
        return type("IsRoleScoped", (cls,), {"roles": roles})

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.has_role(*self.roles))


class IsAdminRole(BasePermission):
    """Admin or super_admin active role, or Django is_superuser. NOT the
    same as DRF's IsAdminUser (which only checks is_staff) — this checks
    our own role system, since is_staff alone must never gate money-moving
    endpoints (see spec: never use is_staff as the sole financial-op guard).
    """

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and (user.is_superuser or user.role in ADMIN_ROLES))


class IsSuperAdmin(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and (user.is_superuser or user.role == "super_admin"))


class IsOwnerOrAdmin(BasePermission):
    """Object-level: the object must have a `user`/`member`/`merchant`/
    `rider`/`agent` attribute pointing back at the requesting user, OR
    the requester must be an admin. Views must still filter querysets by
    owner in the first place (this is a second line of defense against
    IDOR, not a substitute for owner-scoped querysets)."""

    owner_fields = ("user", "member", "merchant", "rider", "agent")

    def has_object_permission(self, request, view, obj):
        user = request.user
        if user.is_superuser or user.role in ADMIN_ROLES:
            return True
        for field in self.owner_fields:
            owner = getattr(obj, field, None)
            if owner is not None:
                owner_user = owner if owner.__class__ is user.__class__ else getattr(owner, "user", None)
                if owner_user == user:
                    return True
        return False


class ReadOnlyOrAdmin(BasePermission):
    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        user = request.user
        return bool(user and user.is_authenticated and (user.is_superuser or user.role in ADMIN_ROLES))


class HasCapability(BasePermission):
    """Usage: permission_classes = [HasCapability.for_capability('agent_manage')]
    Checks a real Django auth.Permission (core.<capability>), never
    is_staff — per spec section 28, is_staff alone must never gate
    sensitive/financial admin operations. SUPER_ADMIN (is_superuser=True)
    always passes."""

    capability = None

    @classmethod
    def for_capability(cls, capability: str):
        return type(f"HasCapability_{capability}", (cls,), {"capability": capability})

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if user.is_superuser:
            return True
        return user.has_perm(f"core.{self.capability}")
