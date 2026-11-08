from django.contrib import admin

from .models import SavingsRecord


@admin.register(SavingsRecord)
class SavingsRecordAdmin(admin.ModelAdmin):
    list_display = ("member", "merchant", "saving_amount", "normal_price", "member_price", "created_at")
    list_filter = ("merchant",)
    search_fields = ("member__user__phone", "merchant__business_name", "claim__code")
    readonly_fields = [f.name for f in SavingsRecord._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
