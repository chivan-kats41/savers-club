from django.contrib import admin

from .models import Subscription, SubscriptionEvent, SubscriptionPayment, SubscriptionPlan


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ("label", "code", "price", "period_days", "is_active", "is_popular")
    list_filter = ("is_active", "is_popular")
    search_fields = ("label", "code")


class SubscriptionPaymentInline(admin.TabularInline):
    model = SubscriptionPayment
    extra = 0
    readonly_fields = ("external_reference", "amount", "status", "provider", "provider_transaction_id", "created_at")

    def has_add_permission(self, request, obj=None):
        return False


class SubscriptionEventInline(admin.TabularInline):
    model = SubscriptionEvent
    extra = 0
    readonly_fields = ("event_type", "metadata", "created_at")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("member", "plan", "status", "current_period_start", "current_period_end", "auto_renew")
    list_filter = ("status", "plan")
    search_fields = ("member__user__phone", "member__user__email")
    autocomplete_fields = ["member", "plan"]
    inlines = [SubscriptionPaymentInline, SubscriptionEventInline]
