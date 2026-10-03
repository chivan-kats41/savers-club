from django.contrib import admin

from .models import Notification, NotificationPreference


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "category", "is_read", "created_at")
    list_filter = ("category", "is_read")
    search_fields = ("title", "user__phone", "user__email")


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = ("user", "sms_enabled", "email_enabled", "in_app_enabled")
    search_fields = ("user__phone", "user__email")
