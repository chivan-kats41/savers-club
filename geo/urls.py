from django.urls import path

from . import views

app_name = "geo"

urlpatterns = [
    path("geo/nearby-deals/", views.NearbyDealsView.as_view(), name="nearby_deals"),
    path("geo/geocode/", views.GeocodeView.as_view(), name="geocode"),
    path("geo/reverse/", views.ReverseGeocodeView.as_view(), name="reverse"),
    path("geo/route/", views.RouteView.as_view(), name="route"),
    path("geo/me/", views.MyLocationView.as_view(), name="me"),
    path("geo/me/ping/", views.LocationPingView.as_view(), name="ping"),
    path("geo/me/history/", views.LocationHistoryView.as_view(), name="history"),
    path("geo/me/history/export/", views.LocationExportView.as_view(), name="history_export"),
    path("geo/me/history/<int:entry_id>/", views.LocationHistoryItemView.as_view(), name="history_item"),
    path("merchant/location/", views.MerchantLocationView.as_view(), name="merchant_location"),
    path("member/delivery/<int:job_id>/track/", views.MemberDeliveryTrackView.as_view(), name="track_delivery"),
    path("rider/location/", views.RiderLocationView.as_view(), name="rider_location"),
    path("rider/jobs/<int:job_id>/nav/", views.RiderJobNavView.as_view(), name="rider_job_nav"),
]
