"""Content-Security-Policy with a per-request nonce.

All scripts/styles/fonts are served from our own origin (see hub/static/hub/vendor),
so the policy can be strict: no CDN hosts, no `unsafe-inline` for scripts, no
`unsafe-eval`. Inline <script>/<style> tags in templates must carry
nonce="{{ csp_nonce }}".
"""
import secrets

from django.conf import settings


class CSPMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.csp_nonce = secrets.token_urlsafe(16)
        response = self.get_response(request)
        if not getattr(settings, "CSP_ENABLED", True) or response.get("Content-Security-Policy"):
            return response
        # Django's own admin and the DRF/Swagger docs use inline scripts/styles
        # and CDN assets; give those paths a relaxed (still same-origin-only
        # for scripts) policy rather than breaking them.
        path = request.path
        relaxed = path.startswith("/django-admin") or path.startswith("/admin/") or path.startswith("/api/docs") or path.startswith("/api/schema")
        nonce = request.csp_nonce
        if relaxed:
            policy = "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' data: https://cdn.redoc.ly; worker-src blob:; frame-ancestors 'none'"
        else:
            policy = "; ".join([
                "default-src 'self'",
                f"script-src 'self' 'nonce-{nonce}'",
                # Inline style="" attributes are used for progress bars; styles can't run code.
                "style-src 'self' 'unsafe-inline'",
                "img-src 'self' data: blob:",
                "font-src 'self'",
                "connect-src 'self'",
                "object-src 'none'",
                "base-uri 'self'",
                "form-action 'self'",
                "frame-ancestors 'none'",
            ])
        if getattr(settings, "CSP_REPORT_ONLY", False):
            response["Content-Security-Policy-Report-Only"] = policy
        else:
            response["Content-Security-Policy"] = policy
        return response


def csp_nonce(request):
    """Template context processor exposing {{ csp_nonce }}."""
    return {"csp_nonce": getattr(request, "csp_nonce", "")}
