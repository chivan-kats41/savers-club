from django.contrib import admin

from .models import Complaint, ComplaintMessage, ComplaintResolution


class ComplaintMessageInline(admin.TabularInline):
    model = ComplaintMessage
    extra = 0
    readonly_fields = ("sender", "message", "created_at")


class ComplaintResolutionInline(admin.StackedInline):
    model = ComplaintResolution
    extra = 0
    readonly_fields = ("resolved_by", "resolution_note", "created_at")


@admin.register(Complaint)
class ComplaintAdmin(admin.ModelAdmin):
    list_display = ("subject", "member", "area", "status", "assigned_agent", "created_at")
    list_filter = ("status", "area")
    search_fields = ("subject", "member__user__phone")
    autocomplete_fields = ["member", "area", "assigned_agent"]
    inlines = [ComplaintMessageInline, ComplaintResolutionInline]
