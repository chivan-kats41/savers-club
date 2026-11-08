from rest_framework import serializers

from .models import PromotionPackage, PromotionPurchase


class PromotionPackageSerializer(serializers.ModelSerializer):
    class Meta:
        model = PromotionPackage
        fields = ["id", "code", "label", "price", "duration_days", "visibility_boost"]


class PromotionPurchaseSerializer(serializers.ModelSerializer):
    package = PromotionPackageSerializer(read_only=True)
    offer_item_name = serializers.CharField(source="offer.item_name", read_only=True)

    class Meta:
        model = PromotionPurchase
        fields = ["id", "offer_item_name", "package", "status", "starts_at", "expires_at", "created_at"]
        read_only_fields = fields
