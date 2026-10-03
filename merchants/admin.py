from django.contrib import admin

from .models import Merchant, MerchantDocument, MerchantVerification


class MerchantDocumentInline(admin.TabularInline):
    model = MerchantDocument
    extra = 0
    readonly_fields = ("doc_type", "file", "uploaded_by", "created_at")

    def has_add_permission(self, request, obj=None):
        return False


class MerchantVerificationInline(admin.TabularInline):
    model = MerchantVerification
    extra = 0
    readonly_fields = ("performed_by", "outcome", "checklist", "notes", "created_at")

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Merchant)
class MerchantAdmin(admin.ModelAdmin):
    list_display = ("business_name", "category", "area", "status", "verified_at")
    list_filter = ("status", "category", "area")
    search_fields = ("business_name", "user__phone", "user__email")
    autocomplete_fields = ["user", "category", "area", "verified_by"]
    readonly_fields = ("verified_by", "verified_at")
    inlines = [MerchantVerificationInline, MerchantDocumentInline]
