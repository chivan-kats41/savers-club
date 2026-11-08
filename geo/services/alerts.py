"""'A hot deal appeared near you' alerts. Strictly opt-in (NotificationPreference.deal_alerts_enabled), at most one a
day per person, never during quiet hours, never by SMS (in-app + push only), and never the same offer twice."""
from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from notifications.models import Notification, NotificationCategory, NotificationPreference
from notifications.services.dispatch import notify

from . import nearby

QUIET_FROM, QUIET_UNTIL = 21, 7      # local hours: no alerts from 21:00 to 07:00
MAX_USERS_PER_RUN = 500


def _ugx(value) -> str:
    return f"UGX {int(round(float(value))):,}"


def send_nearby_deal_alerts(now=None) -> int:
    from hub import selectors   # local import: hub.selectors imports geo, not the other way round

    now = now or timezone.now()
    hour = timezone.localtime(now).hour
    if hour >= QUIET_FROM or hour < QUIET_UNTIL:
        return 0
    sent = 0
    prefs = NotificationPreference.objects.filter(deal_alerts_enabled=True).select_related("user")[:MAX_USERS_PER_RUN]
    for pref in prefs:
        user = pref.user
        if not user.is_active:
            continue
        past = [n.metadata or {} for n in Notification.objects.filter(
            user=user, category=NotificationCategory.OFFER, created_at__gte=now - timedelta(days=7))]
        past = [m for m in past if m.get("kind") == "nearby_deal"]
        if any(m.get("sent_at", "") >= (now - timedelta(hours=24)).isoformat() for m in past):
            continue                                            # already alerted in the last 24 h
        origin = nearby.resolve_origin(user)
        if origin is None:
            continue
        seen = {m.get("offer_id") for m in past}
        for card in selectors.hot_deals_near(origin, limit=5, include_further=False):
            if card["within"] and card["id"] not in seen:
                where = card["distance"] or card["area"]
                notify(
                    user, NotificationCategory.OFFER, f"Hot deal near {origin.label}",
                    f"{card['item']} from {card['seller']}: {_ugx(card['member'])} (save {_ugx(card['saving'])}). {where}.",
                    metadata={"kind": "nearby_deal", "offer_id": card["id"], "sent_at": now.isoformat(),
                              "url": "/member/", "_channels": ["in_app", "push"]},
                )
                sent += 1
                break
    return sent
