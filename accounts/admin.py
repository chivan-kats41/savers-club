from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import EmailVerification, LoginAttempt, PhoneVerification, SecurityEvent, User, UserRole


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    ordering = ["-date_joined"]
    list_display = ("phone", "email", "role", "is_active", "is_staff", "date_joined")
    list_filter = ("role", "is_active", "is_staff", "phone_verified", "email_verified")
    search_fields = ("phone", "email", "first_name", "last_name")

    fieldsets = (
        (None, {"fields": ("phone", "email", "password")}),
        ("Personal info", {"fields": ("first_name", "last_name")}),
        ("Role & verification", {"fields": ("role", "phone_verified", "email_verified")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("phone", "email", "password1", "password2")}),
    )
    readonly_fields = ("date_joined",)


@admin.register(UserRole)
class UserRoleAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "is_active", "assigned_at")
    list_filter = ("role", "is_active")
    search_fields = ("user__phone", "user__email")


@admin.register(LoginAttempt)
class LoginAttemptAdmin(admin.ModelAdmin):
    list_display = ("identifier", "user", "success", "ip_address", "created_at")
    list_filter = ("success",)
    search_fields = ("identifier",)
    readonly_fields = [f.name for f in LoginAttempt._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(SecurityEvent)
class SecurityEventAdmin(admin.ModelAdmin):
    list_display = ("event_type", "user", "ip_address", "created_at")
    list_filter = ("event_type",)
    search_fields = ("user__phone", "user__email")
    readonly_fields = [f.name for f in SecurityEvent._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


admin.site.register(PhoneVerification)
admin.site.register(EmailVerification)
