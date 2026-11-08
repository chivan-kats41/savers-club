from django.utils import timezone

from .models import Offer


def expire_stale_offers() -> int:
    return Offer.objects.filter(
        status=Offer.Status.ACTIVE, expires_at__lte=timezone.now()
    ).update(status=Offer.Status.EXPIRED)
