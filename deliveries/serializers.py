from rest_framework import serializers

from .models import DeliveryJob, RiderEarning, SharedRoute


class DeliveryJobSerializer(serializers.ModelSerializer):
    merchant_name = serializers.CharField(source="pickup_merchant.business_name", read_only=True)
    dropoff_area_name = serializers.CharField(source="dropoff_area.name", read_only=True)

    class Meta:
        model = DeliveryJob
        fields = [
            "id", "status", "delivery_type", "fare", "merchant_name",
            "dropoff_area_name", "dropoff_address", "route", "created_at",
            "assigned_at", "picked_up_at", "delivered_at",
        ]
        read_only_fields = fields


class SharedRouteSerializer(serializers.ModelSerializer):
    origin_area_name = serializers.CharField(source="origin_area.name", read_only=True)
    destination_area_name = serializers.CharField(source="destination_area.name", read_only=True)
    package_count = serializers.IntegerField(source="packages.count", read_only=True)

    class Meta:
        model = SharedRoute
        fields = [
            "id", "origin_area", "destination_area", "origin_area_name", "destination_area_name",
            "departure_time", "max_packages", "package_count", "status", "created_at",
        ]
        read_only_fields = ["id", "package_count", "status", "created_at"]


class RiderEarningSerializer(serializers.ModelSerializer):
    class Meta:
        model = RiderEarning
        fields = ["id", "delivery_job", "gross_amount", "commission_amount", "net_amount", "created_at"]
        read_only_fields = fields
