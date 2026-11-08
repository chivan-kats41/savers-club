"""Sign-in form for /django-admin/.

Django's stock admin login takes its length limit from the USERNAME field, which here is the 20-character phone number,
so a browser silently cut an email like "someone.longname@gmail.com" short and the login failed. This form accepts a phone
number OR an email of any normal length, and, unlike the stock form, it takes part in the same lockout rules as the main
login page (the stock form recorded nothing, so this high-value door had no failed-attempt counter at all).
"""
from django import forms
from django.contrib.admin.forms import AdminAuthenticationForm

from core.middleware import get_client_ip

from .authentication import LOCKOUT_THRESHOLD, LOCKOUT_WINDOW_MINUTES, login_ip_failure_limit
from .models import LoginAttempt
from .phone import canonical_identifier


class PhoneOrEmailAdminLoginForm(AdminAuthenticationForm):
    def __init__(self, request=None, *args, **kwargs):
        super().__init__(request, *args, **kwargs)
        field = self.fields["username"]
        field.max_length = 254                       # an email is allowed; the phone column's 20 was the limit before
        field.label = "Phone or email"
        field.widget.attrs.update({"maxlength": 254, "autocapitalize": "none", "spellcheck": "false",
                                   "placeholder": "Phone number or email"})

    def clean(self):
        username = canonical_identifier(self.cleaned_data.get("username"))
        self.cleaned_data["username"] = username
        ip = get_client_ip(self.request) if self.request is not None else None

        if username and self.cleaned_data.get("password"):
            if (LoginAttempt.recent_failures_from_ip(ip, LOCKOUT_WINDOW_MINUTES) >= login_ip_failure_limit()
                    or LoginAttempt.recent_failures(username, LOCKOUT_WINDOW_MINUTES) >= LOCKOUT_THRESHOLD):
                raise forms.ValidationError(
                    "Too many failed attempts. Please wait a few minutes and try again.", code="locked")
        try:
            cleaned = super().clean()
        except forms.ValidationError:
            if username:
                LoginAttempt.objects.create(identifier=username[:150], ip_address=ip, success=False)
            raise
        LoginAttempt.objects.create(identifier=username[:150], user=self.user_cache, ip_address=ip, success=True)
        return cleaned
