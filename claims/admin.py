from django.contrib import admin

from .models import ClaimEvent, OfferClaim


class ClaimEventInline(admin.TabularInline):
    model = ClaimEvent
    extra = 0
    readonly_fields = ("event_type", "actor", "metadata", "created_at")

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(OfferClaim)
class OfferClaimAdmin(admin.ModelAdmin):
    list_display = ("code", "member", "offer", "status", "expected_saving", "expires_at", "redeemed_at")
    list_filter = ("status",)
    search_fields = ("code", "member__user__phone", "offer__item_name")
    autocomplete_fields = ["member", "offer", "redeemed_by"]
    readonly_fields = ("code", "redemption_attempts")
    inlines = [ClaimEventInline]
