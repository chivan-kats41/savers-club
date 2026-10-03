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

    if prefs.sms_enabled and getattr(user, "phone", ""):
        # Separate task so a provider outage retries only the SMS (never re-sends the email).
        send_sms_notification.delay(user.phone, f"{notification.title}: {notification.message}")

    if prefs.email_enabled and getattr(user, "email", ""):
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
