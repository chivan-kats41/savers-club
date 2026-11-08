from celery import shared_task


@shared_task(name="geo.purge_location_history")
def purge_location_history():
    from .services.history import purge_expired

    return purge_expired()


@shared_task(name="geo.send_nearby_deal_alerts")
def send_nearby_deal_alerts():
    from .services.alerts import send_nearby_deal_alerts as run

    return run()
