from django.urls import path

from . import views

app_name = "payments"

urlpatterns = [
    path("payments/initiate/", views.InitiatePaymentView.as_view(), name="initiate"),
    path("payments/<int:payment_id>/", views.PaymentStatusView.as_view(), name="status"),
    path("payments/callback/iotec/collection/", views.CollectionCallbackView.as_view(), name="iotec_collection_callback"),
    path("payments/callback/iotec/disbursement/", views.DisbursementCallbackView.as_view(), name="iotec_disbursement_callback"),
    path("rider/balance/", views.RiderBalanceView.as_view(), name="rider_balance"),
    path("rider/withdraw/", views.RequestWithdrawalView.as_view(), name="request_withdrawal"),
    path("rider/withdrawals/", views.MyWithdrawalsView.as_view(), name="my_withdrawals"),
]
