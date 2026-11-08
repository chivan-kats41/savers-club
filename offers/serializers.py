from rest_framework import serializers

from .models import Offer, OfferCategory


class OfferCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = OfferCategory
        fields = ["id", "key", "label", "emoji"]


class MerchantOfferSerializer(serializers.ModelSerializer):
    class Meta:
        model = Offer
        fields = [
            "id", "category", "area", "item_name", "normal_price", "member_price",
            "quantity", "pickup_location", "delivery_available", "offer_radius_km",
            "packaging_status", "status", "views_count", "expires_at", "created_at",
        ]
        read_only_fields = ["id", "status", "views_count", "created_at"]


class PublicOfferSerializer(serializers.ModelSerializer):
    merchant_name = serializers.CharField(source="merchant.business_name", read_only=True)
    category_label = serializers.CharField(source="category.label", read_only=True)
    area_name = serializers.CharField(source="area.name", read_only=True)
    possible_saving = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = Offer
        fields = [
            "id", "item_name", "merchant_name", "category_label", "area_name",
            "normal_price", "member_price", "possible_saving", "quantity",
            "delivery_available", "expires_at",
        ]
        read_only_fields = fields
