from celery import shared_task

from .models import Notification
from .services.dispatch import get_or_create_preferences
from .services.email_gateway import send_email_notification
from .services.sms_gateway import SMSTemporaryError, send_sms


@shared_task(name="notifications.dispatch_external")
def dispatch_external_notification(notification_id):
    notification = Notification.objects.select_related("user").filter(pk=notification_id).first()
    if notification is None:
        return

    prefs = get_or_create_preferences(notification.user)
    user = notification.user
    # A notification can restrict where it goes (e.g. promotional "deal near you" alerts: in-app + push, never SMS).
    channels = (notification.metadata or {}).get("_channels")

    def allowed(channel):
        return channels is None or channel in channels

    if prefs.push_enabled and allowed("push"):
        send_push_notification.delay(notification.id)

    if allowed("sms") and prefs.sms_enabled and getattr(user, "phone", ""):
        # Separate task so a provider outage retries only the SMS (never re-sends the email).
        send_sms_notification.delay(user.phone, f"{notification.title}: {notification.message}")

    if allowed("email") and prefs.email_enabled and getattr(user, "email", ""):
        send_email_notification(user.email, notification.title, notification.message)


@shared_task(
    name="notifications.send_sms",
    autoretry_for=(SMSTemporaryError,),
    retry_backoff=30,        # 30s, 60s, 120s…
    retry_backoff_max=900,
    retry_kwargs={"max_retries": 4},
)
def send_sms_notification(phone, text):
    return send_sms(phone, text, raise_transient=True)


@shared_task(name="notifications.send_push")
def send_push_notification(notification_id):
    """Web Push to the user's subscribed devices. A no-op until VAPID keys are configured."""
    from .services.push import push_configured, send_push

    if not push_configured():
        return 0
    notification = Notification.objects.select_related("user").filter(pk=notification_id).first()
    if notification is None:
        return 0
    meta = notification.metadata or {}
    return send_push(notification.user, notification.title, notification.message,
                     url=meta.get("url", "/notifications/"), tag=f"n{notification.pk}")
