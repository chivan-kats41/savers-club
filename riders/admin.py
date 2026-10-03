from django.contrib import admin

from .models import Rider, RiderDocument, RiderVerification


class RiderDocumentInline(admin.TabularInline):
    model = RiderDocument
    extra = 0
    readonly_fields = ("doc_type", "file", "uploaded_by", "created_at")

    def has_add_permission(self, request, obj=None):
        return False


class RiderVerificationInline(admin.TabularInline):
    model = RiderVerification
    extra = 0
    readonly_fields = ("performed_by", "outcome", "checklist", "notes", "created_at")

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Rider)
class RiderAdmin(admin.ModelAdmin):
    list_display = ("user", "area", "vehicle_type", "status", "is_available")
    list_filter = ("status", "vehicle_type", "area")
    search_fields = ("user__phone", "user__email", "plate_number")
    autocomplete_fields = ["user", "area", "verified_by"]
    readonly_fields = ("verified_by", "verified_at")
    inlines = [RiderVerificationInline, RiderDocumentInline]
