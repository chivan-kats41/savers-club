import logging

from rest_framework.views import exception_handler as drf_default_exception_handler

logger = logging.getLogger("django")


def api_exception_handler(exc, context):
    """Wraps DRF's default handler to always return the project-wide
    {"success": false, "error": {"code", "message", "details"}} shape,
    and never leaks internal exception text for unhandled (500-class)
    errors — those get a generic message while the real exception is
    logged server-side.
    """
    response = drf_default_exception_handler(exc, context)

    if response is None:
        # Unhandled exception -> DRF would normally let Django's 500 page
        # take over. Log it and return a safe, generic API error instead.
        logger.exception("Unhandled API exception: %s", exc)
        from rest_framework.response import Response

        return Response(
            {
                "success": False,
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "Something went wrong. Please try again.",
                    "details": {},
                },
            },
            status=500,
        )

    code = getattr(exc, "default_code", exc.__class__.__name__)
    detail = response.data

    # DRF puts validation errors as {field: [errors]} or a plain list/str.
    if isinstance(detail, dict) and "detail" in detail and len(detail) == 1:
        message = str(detail["detail"])
        details = {}
    elif isinstance(detail, dict):
        message = "Validation failed."
        details = detail
    elif isinstance(detail, list):
        message = str(detail[0]) if detail else "Request failed."
        details = {"errors": detail}
    else:
        message = str(detail)
        details = {}

    response.data = {
        "success": False,
        "error": {
            "code": str(code).upper(),
            "message": message,
            "details": details,
        },
    }
    return response
