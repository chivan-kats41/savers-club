from decimal import Decimal, InvalidOperation

from django.conf import settings

from .models import SystemSetting


def get_setting(key: str, default: str = "") -> str:
    row = SystemSetting.objects.filter(key=key, is_active=True).first()
    return row.value if row else default


def get_setting_decimal(key: str, default: Decimal) -> Decimal:
    raw = get_setting(key, str(default))
    try:
        return Decimal(raw)
    except InvalidOperation:
        return default


def get_setting_int(key: str, default: int) -> int:
    raw = get_setting(key, str(default))
    try:
        return int(raw)
    except ValueError:
        return default


def route_commission_percent() -> Decimal:
    return get_setting_decimal(
        "delivery.route_commission_percent", Decimal(str(settings.DEFAULT_ROUTE_COMMISSION_PERCENT))
    )


def reconciliation_timeout_minutes() -> int:
    return get_setting_int("payment.reconciliation_timeout_minutes", 60)


def withdrawal_minimum() -> Decimal:
    return get_setting_decimal("withdrawal.minimum_ugx", Decimal("2000"))


def withdrawal_fee_percent() -> Decimal:
    return get_setting_decimal("withdrawal.fee_percent", Decimal("1.00"))


def record_risk_event(event_type: str, user=None, ip_address: str | None = None, metadata: dict | None = None):
    """Logs a fraud/risk signal for admin review. Deliberately does not
    take any automatic action itself — see spec section 33: 'do not
    automatically block legitimate users based only on one signal'."""
    from .models import RiskEvent

    return RiskEvent.objects.create(
        user=user, event_type=event_type, ip_address=ip_address, metadata=metadata or {}
    )
