from rest_framework import serializers

from merchants.models import Merchant
from riders.models import Rider

from .models import Agent, AgentEarning, PriceRecord


class AgentSerializer(serializers.ModelSerializer):
    areas = serializers.SlugRelatedField(slug_field="name", many=True, read_only=True)

    class Meta:
        model = Agent
        fields = ["id", "areas", "status", "created_at"]
        read_only_fields = fields


class MerchantToVerifySerializer(serializers.ModelSerializer):
    class Meta:
        model = Merchant
        fields = ["id", "business_name", "category", "area", "status", "created_at"]
        read_only_fields = fields


class RiderToVerifySerializer(serializers.ModelSerializer):
    class Meta:
        model = Rider
        fields = ["id", "vehicle_type", "area", "status", "created_at"]
        read_only_fields = fields


class PriceRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = PriceRecord
        fields = ["id", "area", "category", "item_name", "price", "created_at"]
        read_only_fields = ["id", "created_at"]


class AgentEarningSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgentEarning
        fields = ["id", "source", "amount", "reference", "created_at"]
        read_only_fields = fields
