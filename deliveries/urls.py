from django.urls import path

from . import views

app_name = "deliveries"

urlpatterns = [
    path("member/delivery/request/", views.RequestDeliveryView.as_view(), name="request_delivery"),
    path("rider/jobs/", views.AvailableJobsView.as_view(), name="available_jobs"),
    path("rider/jobs/<int:job_id>/accept/", views.AcceptJobView.as_view(), name="accept_job"),
    path("rider/jobs/<int:job_id>/arrived/", views.ArrivedJobView.as_view(), name="arrived_job"),
    path("rider/jobs/<int:job_id>/picked-up/", views.PickedUpJobView.as_view(), name="picked_up_job"),
    path("rider/jobs/<int:job_id>/on-route/", views.OnRouteJobView.as_view(), name="on_route_job"),
    path("rider/jobs/<int:job_id>/delivered/", views.DeliveredJobView.as_view(), name="delivered_job"),
    path("rider/jobs/<int:job_id>/failed/", views.FailedJobView.as_view(), name="failed_job"),
    path("rider/earnings/", views.RiderEarningsView.as_view(), name="rider_earnings"),
    path("rider/routes/", views.RiderRoutesView.as_view(), name="rider_routes"),
    path("rider/routes/<int:route_id>/publish/", views.PublishRouteView.as_view(), name="publish_route"),
    path("rider/routes/<int:route_id>/attach/<int:job_id>/", views.AttachJobToRouteView.as_view(), name="attach_job_to_route"),
    path("rider/routes/<int:route_id>/complete/", views.CompleteRouteView.as_view(), name="complete_route"),
    path("rider/routes/<int:route_id>/cancel/", views.CancelRouteView.as_view(), name="cancel_route"),
]
