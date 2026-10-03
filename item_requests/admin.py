from django.contrib import admin

from .models import MemberRequest, RequestResponse


class RequestResponseInline(admin.TabularInline):
    model = RequestResponse
    extra = 0
    fk_name = "request"
    readonly_fields = ("merchant", "message", "price", "created_at")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(RequestResponse)
class RequestResponseAdmin(admin.ModelAdmin):
    list_display = ("request", "merchant", "price", "created_at")
    search_fields = ("request__item_name", "merchant__business_name")


@admin.register(MemberRequest)
class MemberRequestAdmin(admin.ModelAdmin):
    list_display = ("item_name", "member", "area", "max_budget", "status", "created_at")
    list_filter = ("status", "area")
    search_fields = ("item_name", "member__user__phone")
    autocomplete_fields = ["member", "area", "fulfilled_response"]
    inlines = [RequestResponseInline]
