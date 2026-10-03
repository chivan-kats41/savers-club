from django.contrib import admin

from .models import Member, ReferralReward


@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):
    list_display = ("user", "area", "account_status", "referral_code", "referred_by", "created_at")
    list_filter = ("account_status", "area")
    search_fields = ("user__phone", "user__email", "referral_code")
    autocomplete_fields = ["user", "area", "referred_by"]


@admin.register(ReferralReward)
class ReferralRewardAdmin(admin.ModelAdmin):
    list_display = ("referrer", "referred_member", "amount", "status", "credited_at", "created_at")
    list_filter = ("status",)
    search_fields = ("referrer__user__phone", "referred_member__user__phone")
    autocomplete_fields = ["referrer", "referred_member"]
    readonly_fields = ("referrer", "referred_member", "amount", "created_at")
