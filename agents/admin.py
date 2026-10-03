from django.contrib import admin

from .models import Agent, AgentEarning, PriceRecord


@admin.register(Agent)
class AgentAdmin(admin.ModelAdmin):
    list_display = ("user", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("user__phone", "user__email")
    filter_horizontal = ("areas",)


@admin.register(AgentEarning)
class AgentEarningAdmin(admin.ModelAdmin):
    list_display = ("agent", "source", "amount", "reference", "created_at")
    search_fields = ("agent__user__phone", "reference")
    readonly_fields = [f.name for f in AgentEarning._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(PriceRecord)
class PriceRecordAdmin(admin.ModelAdmin):
    list_display = ("item_name", "area", "category", "price", "agent", "created_at")
    list_filter = ("area", "category")
    search_fields = ("item_name",)
