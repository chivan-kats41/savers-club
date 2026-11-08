"""Web Push (VAPID) delivery to devices that subscribed on purpose.

SSRF guard: the server POSTs to the ``endpoint`` URL the browser gave us, so an attacker could subscribe with an
internal address and make the server call it. Endpoints are therefore accepted only over https and only from the
real push-service hosts (settings.PUSH_ALLOWED_HOST_SUFFIXES), never an IP literal.
"""
from __future__ import annotations

import ipaddress
import json
import logging
from urllib.parse import urlparse

from django.conf import settings
from django.utils import timezone

from ..models import PushSubscription

logger = logging.getLogger("notifications")

DEFAULT_ALLOWED_SUFFIXES = (
    "fcm.googleapis.com",            # Chrome / Edge / Android
    "push.services.mozilla.com",     # Firefox
    "push.apple.com",                # Safari / iOS (web.push.apple.com)
    "notify.windows.com",            # Windows (WNS)
)
MAX_FAILURES = 5


def push_configured() -> bool:
    return bool(settings.VAPID_PUBLIC_KEY and settings.VAPID_PRIVATE_KEY and settings.VAPID_CONTACT)


def allowed_suffixes():
    return tuple(getattr(settings, "PUSH_ALLOWED_HOST_SUFFIXES", DEFAULT_ALLOWED_SUFFIXES))


def endpoint_is_allowed(endpoint: str) -> bool:
    try:
        u = urlparse(str(endpoint))
    except ValueError:
        return False
    host = (u.hostname or "").lower()
    if u.scheme != "https" or not host or u.username or u.password:
        return False
    try:
        ipaddress.ip_address(host)
        return False                                    # no IP literals
    except ValueError:
        pass
    return any(host == s or host.endswith("." + s) for s in allowed_suffixes())


def _send(sub: PushSubscription, payload: dict) -> str:
    """'ok' | 'gone' (subscription dead, delete it) | 'error' (transient)."""
    from pywebpush import WebPushException, webpush

    try:
        webpush(
            subscription_info={"endpoint": sub.endpoint, "keys": {"p256dh": sub.p256dh, "auth": sub.auth}},
            data=json.dumps(payload),
            vapid_private_key=settings.VAPID_PRIVATE_KEY,
            vapid_claims={"sub": settings.VAPID_CONTACT},
            ttl=3600,
            timeout=8,
        )
        return "ok"
    except WebPushException as exc:
        code = getattr(getattr(exc, "response", None), "status_code", None)
        if code in (404, 410):
            return "gone"
        logger.warning("Web push failed (status=%s) for subscription %s", code, sub.pk)
        return "error"
    except Exception:  # never let a push problem break the caller
        logger.exception("Unexpected web push error for subscription %s", sub.pk)
        return "error"


def send_push(user, title: str, body: str, url: str = "/", tag: str = "") -> int:
    """Send to every device of ``user``. Returns how many devices accepted it."""
    if not push_configured():
        return 0
    payload = {"title": str(title)[:80], "body": str(body)[:180], "url": url if str(url).startswith("/") else "/",
               "tag": str(tag)[:64]}
    delivered = 0
    for sub in PushSubscription.objects.filter(user=user):
        if not endpoint_is_allowed(sub.endpoint):
            sub.delete()
            continue
        outcome = _send(sub, payload)
        if outcome == "ok":
            delivered += 1
            PushSubscription.objects.filter(pk=sub.pk).update(last_success_at=timezone.now(), failure_count=0)
        elif outcome == "gone":
            sub.delete()
        else:
            sub.failure_count += 1
            if sub.failure_count >= MAX_FAILURES:
                sub.delete()
            else:
                PushSubscription.objects.filter(pk=sub.pk).update(failure_count=sub.failure_count)
    return delivered
