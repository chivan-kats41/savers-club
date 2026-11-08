from rest_framework import serializers

from .models import OfferClaim


class ClaimSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source="offer.item_name", read_only=True)
    merchant_name = serializers.CharField(source="offer.merchant.business_name", read_only=True)

    class Meta:
        model = OfferClaim
        fields = [
            "id", "code", "status", "expected_saving", "expires_at",
            "redeemed_at", "item_name", "merchant_name", "created_at",
        ]
        read_only_fields = fields


class MerchantClaimSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source="offer.item_name", read_only=True)
    member_name = serializers.SerializerMethodField()

    class Meta:
        model = OfferClaim
        fields = ["id", "code", "status", "item_name", "member_name", "created_at", "redeemed_at"]
        read_only_fields = fields

    def get_member_name(self, obj):
        return obj.member.user.get_full_name()
