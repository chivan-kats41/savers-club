import uuid


class AuditRequestMiddleware:
    """Attaches a short-lived request_id to every request so views/services
    can stamp AuditLog rows and log lines with a correlation ID. This
    middleware does not itself write audit rows — specific sensitive
    actions (login, payment, redemption, admin changes, ...) create their
    own AuditLog entries in later phases and read request.request_id.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.request_id = uuid.uuid4().hex
        response = self.get_response(request)
        response["X-Request-ID"] = request.request_id
        return response


def get_client_ip(request):
    """The real client address.

    X-Forwarded-For is client-controlled until a proxy we trust has written to it, so it is only read when
    settings.TRUSTED_PROXY_COUNT says how many trusted proxies sit in front of us (1 behind nginx / the
    PythonAnywhere front end, 0 when Django is reached directly). The address is then taken from the RIGHT of
    the header: the entry our own proxy appended, never the left-most one a visitor can forge.
    """
    from django.conf import settings

    trusted = int(getattr(settings, "TRUSTED_PROXY_COUNT", 0) or 0)
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if trusted > 0 and forwarded:
        hops = [h.strip() for h in forwarded.split(",") if h.strip()]
        if hops:
            return hops[-min(trusted, len(hops))]
    return request.META.get("REMOTE_ADDR")
