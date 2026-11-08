from rest_framework import serializers

from .models import Subscription, SubscriptionPayment, SubscriptionPlan


class SubscriptionPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionPlan
        fields = ["code", "label", "price", "period_days", "is_popular", "benefits"]


class SubscriptionPaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionPayment
        fields = ["external_reference", "amount", "status", "created_at"]


class SubscriptionSerializer(serializers.ModelSerializer):
    plan = SubscriptionPlanSerializer(read_only=True)
    latest_payment = serializers.SerializerMethodField()

    class Meta:
        model = Subscription
        fields = [
            "id", "plan", "status", "current_period_start", "current_period_end",
            "auto_renew", "latest_payment",
        ]

    def get_latest_payment(self, obj):
        payment = obj.payments.order_by("-created_at").first()
        return SubscriptionPaymentSerializer(payment).data if payment else None
