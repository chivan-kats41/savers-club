from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from payments.views import IotecCallbackView as PaymentsIotecCallbackView
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView

from core.views import health, health_live, health_ready

urlpatterns = [
    path("django-admin/", admin.site.urls),
    path("health/", health, name="health"),
    path("health/live/", health_live, name="health_live"),
    path("health/ready/", health_ready, name="health_ready"),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger_ui"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
    path("api/v1/", include("subscriptions.urls")),
    path("api/v1/", include("offers.urls")),
    path("api/v1/", include("members.urls")),
    path("api/v1/", include("item_requests.urls")),
    path("api/v1/", include("promotions.urls")),
    path("api/v1/", include("claims.urls")),
    path("api/v1/", include("savings.urls")),
    path("api/v1/", include("deliveries.urls")),
    path("api/v1/", include("payments.urls")),
    # The ONE callback URL to register in the ioTec Pay portal (collections + disbursements).
    # Both spellings: ioTec posts exactly what you typed, and Django cannot redirect a POST.
    path("api/iotec/callback", PaymentsIotecCallbackView.as_view(), name="iotec_callback_noslash"),
    path("api/iotec/callback/", PaymentsIotecCallbackView.as_view(), name="iotec_callback"),
    path("api/v1/", include("accounts.api_urls")),
    path("api/v1/", include("core.api_urls")),
    path("api/v1/", include("agents.urls")),
    path("api/v1/", include("complaints.urls")),
    path("api/v1/", include("notifications.urls")),
    path("api/v1/", include("hub.api_urls")),
    path("accounts/", include("accounts.urls")),
    path("", include("hub.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

if settings.DEBUG:
    urlpatterns += staticfiles_urlpatterns()
