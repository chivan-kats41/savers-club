from functools import wraps

from django.core.cache import cache
from django.http import HttpResponse

from .middleware import get_client_ip


def rate_limit(key_prefix: str, limit: int, period_seconds: int):
    """Sliding-window-ish limiter keyed by client IP. Not a substitute for
    DRF's ScopedRateThrottle (used on the API layer) — this exists for
    the server-rendered accounts views (register, password reset, OTP
    resend), which aren't DRF APIViews and so never got throttle_classes.
    """

    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            ip = get_client_ip(request) or "unknown"
            cache_key = f"ratelimit:{key_prefix}:{ip}"
            count = cache.get(cache_key, 0)
            if count >= limit:
                return HttpResponse("Too many requests. Please try again later.", status=429)
            cache.set(cache_key, count + 1, timeout=period_seconds)
            return view_func(request, *args, **kwargs)

        return wrapped

    return decorator
