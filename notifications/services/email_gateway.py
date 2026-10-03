import logging

from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger("notifications")


def send_email_notification(to_email: str, subject: str, message: str) -> bool:
    if not to_email:
        return False
    try:
        send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [to_email])
        return True
    except Exception:
        logger.exception("Email send failed for to_email=%s", to_email)
        return False
