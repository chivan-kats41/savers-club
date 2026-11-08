from django.conf import settings

from notifications.services.push import push_configured


def geo_config(request):
    """Map/push settings every page can hand to the front end (see hub/partials/geo_assets.html)."""
    return {"geo_config": {
        "tile_url": settings.MAP_TILE_URL,
        "attribution": settings.MAP_TILE_ATTRIBUTION,
        "tile_referrer_policy": settings.MAP_TILE_REFERRER_POLICY,
        "center_lat": settings.MAP_DEFAULT_CENTER[0],
        "center_lng": settings.MAP_DEFAULT_CENTER[1],
        "vapid_public_key": settings.VAPID_PUBLIC_KEY if push_configured() else "",
    }}
