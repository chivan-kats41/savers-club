from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("register/", views.register, name="register"),
    path("verify-phone/", views.verify_phone, name="verify_phone"),
    path("verify-phone/resend/", views.resend_phone_otp, name="resend_phone_otp"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("password-reset/", views.password_reset_request, name="password_reset_request"),
    path("password-reset/confirm/", views.password_reset_confirm, name="password_reset_confirm"),
    path("switch-role/", views.switch_role, name="switch_role"),
    path("2fa/setup/", views.twofa_setup, name="2fa_setup"),
    path("2fa/verify/", views.twofa_verify, name="2fa_verify"),
]
