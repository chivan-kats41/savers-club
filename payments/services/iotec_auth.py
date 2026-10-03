import logging

import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger("payments")

TOKEN_CACHE_KEY = "iotec:access_token"
DEFAULT_TOKEN_TTL_SECONDS = 300  # per ioTec docs; refreshed early via the safety margin below
REFRESH_SAFETY_MARGIN_SECONDS = 30


class IotecAuthError(Exception):
    pass


def get_access_token(force_refresh: bool = False) -> str:
    """Returns a cached access token, fetching a new one if absent/expired.
    Never logs the token or the client secret."""
    if not force_refresh:
        cached = cache.get(TOKEN_CACHE_KEY)
        if cached:
            return cached

    if not settings.IOTEC_CLIENT_ID or not settings.IOTEC_CLIENT_SECRET:
        raise IotecAuthError("IOTEC_CLIENT_ID / IOTEC_CLIENT_SECRET are not configured.")

    try:
        resp = requests.post(
            settings.IOTEC_TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": settings.IOTEC_CLIENT_ID,
                "client_secret": settings.IOTEC_CLIENT_SECRET,
            },
            timeout=10,
        )
    except requests.RequestException as exc:
        logger.error("ioTec auth request failed: %s", exc)
        raise IotecAuthError("Could not reach ioTec auth endpoint.") from exc

    if resp.status_code != 200:
        logger.error("ioTec auth failed with status=%s", resp.status_code)
        raise IotecAuthError(f"ioTec auth failed (status {resp.status_code}).")

    data = resp.json()
    access_token = data.get("access_token")
    if not access_token:
        raise IotecAuthError("ioTec auth response did not include an access_token.")

    expires_in = int(data.get("expires_in", DEFAULT_TOKEN_TTL_SECONDS))
    ttl = max(expires_in - REFRESH_SAFETY_MARGIN_SECONDS, 30)
    cache.set(TOKEN_CACHE_KEY, access_token, timeout=ttl)
    return access_token
