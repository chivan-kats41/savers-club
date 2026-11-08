from django.urls import path

from . import api

app_name = "hub_api"

urlpatterns = [
    path("merchant/apply/", api.MerchantApplyView.as_view(), name="merchant_apply"),
    path("rider/apply/", api.RiderApplyView.as_view(), name="rider_apply"),
    path("rider/documents/", api.RiderDocumentsView.as_view(), name="rider_documents"),
    path("merchant/offers/<int:offer_id>/image/", api.OfferImageView.as_view(), name="offer_image"),
    path("member/offers/<int:offer_id>/interact/", api.OfferInteractView.as_view(), name="offer_interact"),
    path("notifications/read-all/", api.MarkAllReadView.as_view(), name="read_all"),
    path("agent/tasks/<int:task_id>/complete/", api.AgentCompleteTaskView.as_view(), name="task_complete"),
    path("admin/offers/<int:offer_id>/<str:action>/", api.AdminOfferActionView.as_view(), name="admin_offer_action"),
    path("admin/merchants/<int:pk>/verify/", api.AdminVerifyMerchantView.as_view(), name="admin_verify_merchant"),
    path("admin/riders/<int:pk>/verify/", api.AdminVerifyRiderView.as_view(), name="admin_verify_rider"),
    path("admin/settings/<str:key>/", api.AdminSettingView.as_view(), name="admin_setting"),
    path("admin/plans/<int:plan_id>/", api.AdminPlanView.as_view(), name="admin_plan"),
    path("admin/areas/", api.AdminAreasView.as_view(), name="admin_areas"),
    path("admin/areas/<int:area_id>/toggle/", api.AdminAreaToggleView.as_view(), name="admin_area_toggle"),
    path("admin/categories/", api.AdminCategoriesView.as_view(), name="admin_categories"),
    path("admin/pickup-points/", api.AdminPickupPointsView.as_view(), name="admin_pickup_points"),
    path("admin/pickup-points/<int:pp_id>/toggle/", api.AdminPickupToggleView.as_view(), name="admin_pickup_toggle"),
    path("admin/agent-tasks/", api.AdminAgentTasksView.as_view(), name="admin_agent_tasks"),
    path("admin/agent-tasks/<int:task_id>/cancel/", api.AdminAgentTaskCancelView.as_view(), name="admin_agent_task_cancel"),
    path("admin/notifications/broadcast/", api.AdminBroadcastView.as_view(), name="admin_broadcast"),
]
