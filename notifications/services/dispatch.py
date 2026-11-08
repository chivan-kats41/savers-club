import logging

from ..models import Notification, NotificationPreference

logger = logging.getLogger("notifications")


def notify(user, category: str, title: str, message: str, metadata: dict | None = None) -> Notification:
    """Creates the in-app Notification row immediately (cheap, DB-only)
    and queues SMS/email dispatch asynchronously — never blocks the
    calling request/transaction on a network call to a provider.

    Queueing itself must never break the caller: if the Celery broker is
    unreachable (down, not yet provisioned, etc.), the in-app row still
    gets created and the request that triggered this (registration,
    claim redemption, a payment webhook, ...) still succeeds — only the
    SMS/email leg is lost, and that's logged loudly rather than raised.
    """
    notification = Notification.objects.create(
        user=user, category=category, title=title, message=message, metadata=metadata or {}
    )
    from ..tasks import dispatch_external_notification

    try:
        dispatch_external_notification.delay(notification.id)
    except Exception:
        logger.exception(
            "Could not queue notification dispatch (id=%s) — broker unreachable? "
            "The in-app notification was still created.",
            notification.id,
        )
    return notification


def get_or_create_preferences(user) -> NotificationPreference:
    prefs, _ = NotificationPreference.objects.get_or_create(user=user)
    return prefs
