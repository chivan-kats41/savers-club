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
    """Best-effort client IP extraction, respecting a trusted proxy header
    when present (set SECURE_PROXY_SSL_HEADER-style trust at the proxy)."""
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")
