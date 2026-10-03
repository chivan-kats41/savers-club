from django.contrib import admin

from .models import Offer, OfferCategory, OfferImage, OfferInteraction


@admin.register(OfferCategory)
class OfferCategoryAdmin(admin.ModelAdmin):
    list_display = ("label", "key", "emoji", "is_active")
    search_fields = ("label", "key")


class OfferImageInline(admin.TabularInline):
    model = OfferImage
    extra = 0


@admin.register(Offer)
class OfferAdmin(admin.ModelAdmin):
    list_display = (
        "item_name", "merchant", "category", "area", "normal_price", "member_price",
        "quantity", "status", "expires_at",
    )
    list_filter = ("status", "category", "area")
    search_fields = ("item_name", "merchant__business_name")
    autocomplete_fields = ["merchant", "category", "area"]
    readonly_fields = ("views_count", "visibility_score")
    inlines = [OfferImageInline]


@admin.register(OfferInteraction)
class OfferInteractionAdmin(admin.ModelAdmin):
    list_display = ("offer", "kind", "user", "created_at")
    list_filter = ("kind",)
    readonly_fields = [f.name for f in OfferInteraction._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
