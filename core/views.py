from django.db import connections
from django.db.utils import OperationalError
from django.http import JsonResponse


def health(request):
    """Overall liveness+readiness in one call — cheap DB ping."""
    db_ok = True
    try:
        connections["default"].cursor()
    except OperationalError:
        db_ok = False
    status = 200 if db_ok else 503
    return JsonResponse({"status": "ok" if db_ok else "degraded", "database": db_ok}, status=status)


def health_live(request):
    return JsonResponse({"status": "ok"})


def health_ready(request):
    try:
        connections["default"].cursor()
        return JsonResponse({"status": "ready"})
    except OperationalError:
        return JsonResponse({"status": "not-ready"}, status=503)
