from rest_framework import serializers

from .models import Member, ReferralReward


class ReferralRewardSerializer(serializers.ModelSerializer):
    referred_member_name = serializers.CharField(source="referred_member.user.get_full_name", read_only=True)

    class Meta:
        model = ReferralReward
        fields = ["id", "referred_member_name", "amount", "status", "created_at", "credited_at"]
        read_only_fields = fields
