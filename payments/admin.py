from django.contrib import admin

from .models import LedgerEntry, Payment, PaymentCallback, Withdrawal, WithdrawalCallback


class PaymentCallbackInline(admin.TabularInline):
    model = PaymentCallback
    extra = 0
    readonly_fields = ("raw_payload", "provider_status", "processed", "processing_notes", "created_at")

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("internal_reference", "user", "purpose", "method", "amount", "status", "created_at")
    list_filter = ("status", "method", "purpose")
    search_fields = ("internal_reference", "provider_transaction_id", "user__phone", "user__email")
    readonly_fields = ("internal_reference", "provider_transaction_id", "status")
    inlines = [PaymentCallbackInline]


@admin.register(LedgerEntry)
class LedgerEntryAdmin(admin.ModelAdmin):
    list_display = ("user", "direction", "amount", "fee", "net_amount", "created_at")
    list_filter = ("direction",)
    search_fields = ("user__phone", "reference")
    readonly_fields = [f.name for f in LedgerEntry._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class WithdrawalCallbackInline(admin.TabularInline):
    model = WithdrawalCallback
    extra = 0
    readonly_fields = ("raw_payload", "provider_status", "provider_transaction_id", "processed", "processing_notes", "created_at")

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Withdrawal)
class WithdrawalAdmin(admin.ModelAdmin):
    list_display = ("internal_reference", "user", "amount", "fee", "net_amount", "status", "created_at")
    list_filter = ("status", "source")
    search_fields = ("internal_reference", "provider_transaction_id", "user__phone")
    readonly_fields = ("internal_reference", "provider_transaction_id", "status", "completed_at")
    inlines = [WithdrawalCallbackInline]
