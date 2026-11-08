from rest_framework import serializers

from .models import Payment, Withdrawal


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = [
            "id", "purpose", "method", "amount", "currency", "status",
            "internal_reference", "redirect_url", "created_at",
        ]
        read_only_fields = fields


class WithdrawalSerializer(serializers.ModelSerializer):
    class Meta:
        model = Withdrawal
        fields = [
            "id", "amount", "fee", "net_amount", "phone", "status",
            "internal_reference", "created_at", "completed_at",
        ]
        read_only_fields = fields
