from django.contrib import admin

from .models import PromotionPackage, PromotionPurchase


@admin.register(PromotionPackage)
class PromotionPackageAdmin(admin.ModelAdmin):
    list_display = ("label", "code", "price", "duration_days", "visibility_boost", "is_active")
    list_filter = ("is_active",)
    search_fields = ("label", "code")


@admin.register(PromotionPurchase)
class PromotionPurchaseAdmin(admin.ModelAdmin):
    list_display = ("offer", "merchant", "package", "status", "starts_at", "expires_at")
    list_filter = ("status",)
    search_fields = ("merchant__business_name", "offer__item_name")
    autocomplete_fields = ["merchant", "offer", "package"]
    readonly_fields = ("status", "starts_at", "expires_at")
