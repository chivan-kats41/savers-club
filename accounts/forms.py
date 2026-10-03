from django import forms
from django.contrib.auth.password_validation import validate_password

from core.models import Area

from .models import User

INPUT_CLASS = (
    "w-full rounded-lg border border-input bg-background px-3 py-2 text-sm "
    "text-foreground placeholder:text-muted-foreground focus:outline-none "
    "focus:ring-2 focus:ring-ring"
)


class StyledFormMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            existing = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = f"{existing} {INPUT_CLASS}".strip()


class RegisterForm(StyledFormMixin, forms.Form):
    phone = forms.CharField(max_length=20)
    email = forms.EmailField(required=False)
    first_name = forms.CharField(max_length=150, required=False)
    last_name = forms.CharField(max_length=150, required=False)
    area = forms.ModelChoiceField(queryset=Area.objects.filter(is_active=True), empty_label="Select your area")
    referral_code = forms.CharField(max_length=16, required=False)
    password = forms.CharField(widget=forms.PasswordInput)
    password_confirm = forms.CharField(widget=forms.PasswordInput)

    def clean_phone(self):
        phone = self.cleaned_data["phone"].strip()
        if User.objects.filter(phone=phone).exists():
            raise forms.ValidationError("An account with this phone number already exists.")
        return phone

    def clean_email(self):
        email = self.cleaned_data.get("email", "").strip()
        if email and User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email or None

    def clean_password(self):
        password = self.cleaned_data["password"]
        validate_password(password)
        return password

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("password") and cleaned.get("password_confirm"):
            if cleaned["password"] != cleaned["password_confirm"]:
                self.add_error("password_confirm", "Passwords do not match.")
        return cleaned


class LoginForm(StyledFormMixin, forms.Form):
    identifier = forms.CharField(label="Phone or email")
    password = forms.CharField(widget=forms.PasswordInput)


class PhoneVerifyForm(StyledFormMixin, forms.Form):
    code = forms.CharField(max_length=4, min_length=4)


class PasswordResetRequestForm(StyledFormMixin, forms.Form):
    identifier = forms.CharField(label="Phone or email")


class PasswordResetConfirmForm(StyledFormMixin, forms.Form):
    code = forms.CharField(max_length=4, min_length=4)
    new_password = forms.CharField(widget=forms.PasswordInput)
    new_password_confirm = forms.CharField(widget=forms.PasswordInput)

    def clean_new_password(self):
        password = self.cleaned_data["new_password"]
        validate_password(password)
        return password

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("new_password") and cleaned.get("new_password_confirm"):
            if cleaned["new_password"] != cleaned["new_password_confirm"]:
                self.add_error("new_password_confirm", "Passwords do not match.")
        return cleaned
