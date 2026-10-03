from django.contrib import admin

from .models import Area, AuditLog, RiskEvent, SystemSetting


@admin.register(Area)
class AreaAdmin(admin.ModelAdmin):
    list_display = ("name", "is_launch_area", "is_active", "updated_at")
    list_filter = ("is_launch_area", "is_active")
    search_fields = ("name",)


@admin.register(SystemSetting)
class SystemSettingAdmin(admin.ModelAdmin):
    list_display = ("key", "value", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("key", "description")


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "actor", "action", "object_type", "object_id", "ip_address")
    list_filter = ("action", "object_type")
    search_fields = ("action", "object_type", "object_id", "actor__phone", "actor__email")
    readonly_fields = [f.name for f in AuditLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(RiskEvent)
class RiskEventAdmin(admin.ModelAdmin):
    list_display = ("event_type", "user", "ip_address", "reviewed", "created_at")
    list_filter = ("event_type", "reviewed")
    search_fields = ("user__phone", "user__email", "ip_address")
    readonly_fields = ("user", "event_type", "ip_address", "metadata", "created_at")

    def has_add_permission(self, request):
        return False
