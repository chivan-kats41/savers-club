from rest_framework import serializers

from .models import Complaint, ComplaintMessage


class ComplaintMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ComplaintMessage
        fields = ["id", "sender", "message", "created_at"]
        read_only_fields = fields


class ComplaintSerializer(serializers.ModelSerializer):
    class Meta:
        model = Complaint
        fields = ["id", "subject", "description", "status", "area", "created_at"]
        read_only_fields = ["id", "status", "area", "created_at"]
