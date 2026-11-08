from rest_framework import serializers

from .models import MemberRequest, RequestResponse


class RequestResponseSerializer(serializers.ModelSerializer):
    merchant_name = serializers.CharField(source="merchant.business_name", read_only=True)

    class Meta:
        model = RequestResponse
        fields = ["id", "merchant_name", "message", "price", "created_at"]
        read_only_fields = fields


class MemberRequestSerializer(serializers.ModelSerializer):
    responses = RequestResponseSerializer(many=True, read_only=True)
    response_count = serializers.IntegerField(source="responses.count", read_only=True)

    class Meta:
        model = MemberRequest
        fields = [
            "id", "item_name", "description", "max_budget", "status",
            "response_count", "responses", "created_at",
        ]
        read_only_fields = ["id", "status", "response_count", "responses", "created_at"]


class MerchantVisibleRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = MemberRequest
        fields = ["id", "item_name", "description", "max_budget", "status", "created_at"]
        read_only_fields = fields
