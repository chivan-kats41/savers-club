from django.contrib import admin

from .models import DeliveryJob, DeliveryOTP, DeliveryStatusHistory, RiderEarning, SharedRoute


class DeliveryStatusHistoryInline(admin.TabularInline):
    model = DeliveryStatusHistory
    extra = 0
    readonly_fields = ("from_status", "to_status", "changed_by", "notes", "created_at")

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(SharedRoute)
class SharedRouteAdmin(admin.ModelAdmin):
    list_display = ("rider", "origin_area", "destination_area", "departure_time", "max_packages", "status")
    list_filter = ("status", "origin_area", "destination_area")
    search_fields = ("rider__user__phone",)
    autocomplete_fields = ["rider", "origin_area", "destination_area"]


@admin.register(DeliveryJob)
class DeliveryJobAdmin(admin.ModelAdmin):
    list_display = ("id", "pickup_merchant", "dropoff_area", "delivery_type", "status", "rider", "route", "fare")
    list_filter = ("status", "delivery_type", "dropoff_area")
    search_fields = ("pickup_merchant__business_name", "dropoff_address")
    autocomplete_fields = ["pickup_merchant", "dropoff_area", "rider", "route"]
    inlines = [DeliveryStatusHistoryInline]


@admin.register(DeliveryOTP)
class DeliveryOTPAdmin(admin.ModelAdmin):
    list_display = ("job", "is_used", "attempts", "expires_at")
    readonly_fields = [f.name for f in DeliveryOTP._meta.fields]

    def has_add_permission(self, request):
        return False


@admin.register(RiderEarning)
class RiderEarningAdmin(admin.ModelAdmin):
    list_display = ("rider", "delivery_job", "gross_amount", "commission_amount", "net_amount", "created_at")
    search_fields = ("rider__user__phone",)
    readonly_fields = [f.name for f in RiderEarning._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
