from django import template

register = template.Library()

_POSITIVE = {"active", "verified", "success", "delivered", "resolved", "completed", "redeemed", "live"}
_WARNING = {"pending", "waiting rider", "waiting agent", "loading", "in progress", "scheduled", "soft launch", "paused"}
_NEGATIVE = {"suspended", "failed", "expired", "reported", "suspicious", "escalated", "overdue"}
_NEUTRAL = {"used", "draft", "pilot"}


@register.filter
def ugx(amount):
    """UGX 1,234 — port of lib/format.ts ugx()."""
    try:
        amount = round(float(amount))
    except (TypeError, ValueError):
        return amount
    return "UGX " + f"{amount:,}"


@register.filter
def money(amount, currency="UGX"):
    """1,234 with an explicit currency code: {{ wallet.balance|money:wallet.currency }}"""
    try:
        amount = round(float(amount))
    except (TypeError, ValueError):
        return amount
    return f"{currency} {amount:,}"


@register.filter
def ugx_short(amount):
    """UGX 1.2M / UGX 3K — port of lib/format.ts ugxShort()."""
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        return amount
    if amount >= 1_000_000:
        return f"UGX {amount / 1_000_000:.1f}M"
    if amount >= 1_000:
        return f"UGX {amount / 1_000:.0f}K"
    return f"UGX {amount:.0f}"


@register.filter
def badge_class(status):
    """Tailwind classes for a status pill, matched by keyword."""
    key = str(status).strip().lower()
    if key in _POSITIVE:
        return "bg-success/15 text-success-foreground"
    if key in _WARNING:
        return "bg-warning/15 text-warning-foreground"
    if key in _NEGATIVE:
        return "bg-destructive/10 text-destructive"
    if key in _NEUTRAL:
        return "bg-muted text-muted-foreground"
    return "bg-primary-soft text-primary"


@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)


@register.filter
def sub(a, b):
    try:
        return a - b
    except TypeError:
        return ""


@register.filter
def percent_of(part, whole):
    try:
        return round(100 * float(part) / float(whole))
    except (TypeError, ValueError, ZeroDivisionError):
        return 0
