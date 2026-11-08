"""Sign in with a phone number OR an email, everywhere a person can sign in, and a way for everyone to have an email."""
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.admin_forms import PhoneOrEmailAdminLoginForm
from accounts.models import LoginAttempt, Role, SecurityEvent, User
from core.models import Area

PASSWORD = "Pass12345!x"
LONG = "chivankats.longname.testing@gmail.com"            # 38 chars: longer than the 20-char phone column


class Base(TestCase):
    def setUp(self):
        cache.clear()
        self.area = Area.objects.create(name="Kireka")

    def signed_in(self):
        return "_auth_user_id" in self.client.session

    def login(self, identifier, password=PASSWORD):
        return self.client.post(reverse("accounts:login"), {"identifier": identifier, "password": password})

    def member(self, phone="+256772100001", email="jane@example.com", verified=True, **kw):
        return User.objects.create_user(phone=phone, email=email, password=PASSWORD, role=Role.MEMBER,
                                        phone_verified=verified, **kw)


class MainLoginTests(Base):
    def test_email_in_any_spelling_signs_in(self):
        self.member(email="Jane.Doe+tips@Sub.Example.co.ug")
        for ident in ("jane.doe+tips@sub.example.co.ug", "JANE.DOE+TIPS@SUB.EXAMPLE.CO.UG", "  Jane.Doe+tips@Sub.Example.co.ug  "):
            self.client.logout()
            self.login(ident)
            self.assertTrue(self.signed_in(), ident)

    def test_phone_in_any_spelling_still_signs_in(self):
        self.member()
        for ident in ("+256772100001", "0772100001", "772100001", "0772 100 001"):
            self.client.logout()
            self.login(ident)
            self.assertTrue(self.signed_in(), ident)

    def test_a_long_email_is_fine_on_the_main_login_page(self):
        self.member(email=LONG)
        self.login(LONG)
        self.assertTrue(self.signed_in())

    def test_the_same_person_can_use_either_way_with_the_same_password(self):
        self.member()
        self.login("jane@example.com"); self.assertTrue(self.signed_in())
        self.client.logout()
        self.login("0772100001"); self.assertTrue(self.signed_in())

    def test_a_wrong_password_by_email_is_refused_without_revealing_anything(self):
        self.member()
        r = self.login("jane@example.com", "wrong")
        self.assertContains(r, "Invalid credentials")
        self.assertFalse(self.signed_in())
        r2 = self.login("nobody@example.com", "wrong")                          # an unknown email answers the same way
        self.assertContains(r2, "Invalid credentials")

    def test_an_unverified_phone_must_verify_even_when_signing_in_by_email(self):
        self.member(verified=False)
        r = self.login("jane@example.com")
        self.assertRedirects(r, reverse("accounts:verify_phone"), fetch_redirect_response=False)
        self.assertFalse(self.signed_in())

    def test_the_login_page_says_either_works_and_the_input_is_set_up_for_both(self):
        html = self.client.get(reverse("accounts:login")).content.decode()
        self.assertIn("<strong>or</strong> your email", html)
        self.assertIn('autocomplete="username"', html)
        self.assertIn('autocapitalize="none"', html)
        self.assertNotIn('type="tel"', html)                                    # a phone-only keyboard would block emails
        self.assertNotIn("maxlength", html.split('name="identifier"')[1].split(">")[0])


class AdminLoginTests(Base):
    """/django-admin/login/ used to cap the username at the phone column's 20 characters."""

    def setUp(self):
        super().setUp()
        self.staff = User.objects.create_superuser(phone="+256772200001", email=LONG, password=PASSWORD)

    def admin_login(self, ident, password=PASSWORD, **extra):
        return self.client.post("/django-admin/login/", {"username": ident, "password": password, "next": "/django-admin/"}, **extra)

    def test_the_form_no_longer_limits_the_username_to_20_characters(self):
        form = PhoneOrEmailAdminLoginForm()
        self.assertEqual(form.fields["username"].max_length, 254)
        html = self.client.get("/django-admin/login/").content.decode()
        self.assertIn('maxlength="254"', html)
        self.assertNotIn('maxlength="20"', html)

    @override_settings(ADMIN_REQUIRE_2FA=False)
    def test_a_staff_user_signs_in_with_a_long_email(self):
        r = self.admin_login(LONG)
        self.assertEqual(r.status_code, 302)
        self.assertTrue(self.signed_in())

    @override_settings(ADMIN_REQUIRE_2FA=False)
    def test_and_with_their_phone_in_any_spelling_or_an_uppercase_email(self):
        for ident in ("+256772200001", "0772200001", LONG.upper()):
            self.client.logout()
            self.admin_login(ident)
            self.assertTrue(self.signed_in(), ident)

    def test_a_non_staff_user_cannot_use_it_even_with_the_right_password(self):
        self.member(phone="+256772200002", email="plain@example.com")
        self.admin_login("plain@example.com")
        self.assertFalse(self.signed_in())

    def test_failed_admin_logins_are_recorded_and_lock_the_account(self):
        for _ in range(5):
            self.admin_login(LONG, "wrong")
        self.assertEqual(LoginAttempt.objects.filter(identifier=LONG.lower(), success=False).count(), 5)
        r = self.admin_login(LONG)                                               # even the right password is now refused
        self.assertContains(r, "Too many failed attempts")
        self.assertFalse(self.signed_in())

    def test_the_lock_is_shared_with_the_main_login_page(self):
        for _ in range(5):
            self.login(LONG, "wrong")
        self.assertContains(self.admin_login(LONG), "Too many failed attempts")

    def test_the_network_ceiling_applies_here_too(self):
        LoginAttempt.objects.bulk_create([LoginAttempt(identifier=f"x{i}@example.com", ip_address="10.9.8.7", success=False) for i in range(40)])
        self.assertContains(self.admin_login(LONG, REMOTE_ADDR="10.9.8.7"), "Too many failed attempts")

    @override_settings(ADMIN_REQUIRE_2FA=False)
    def test_successful_admin_logins_are_recorded_too(self):
        self.admin_login(LONG)
        self.assertTrue(LoginAttempt.objects.filter(identifier=LONG.lower(), success=True, user=self.staff).exists())


class AccountPageTests(Base):
    URL = "/accounts/account/"

    def setUp(self):
        super().setUp()
        self.user = self.member(email=None)
        self.client.force_login(self.user)

    def save(self, email, password=PASSWORD):
        return self.client.post(self.URL, {"email": email, "password": password})

    def test_it_needs_a_login(self):
        self.client.logout()
        r = self.client.get(self.URL)
        self.assertEqual(r.status_code, 302)
        self.assertIn("/accounts/login", r["Location"])

    def test_it_shows_how_you_sign_in(self):
        html = self.client.get(self.URL).content.decode()
        self.assertIn("+256772100001", html)
        self.assertIn("not set", html)
        self.assertIn("either works", html)

    def test_adding_an_email_lets_the_person_sign_in_with_it(self):
        r = self.save("New.Person@Example.com")
        self.assertRedirects(r, self.URL, fetch_redirect_response=False)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "new.person@example.com")             # one spelling
        self.assertFalse(self.user.email_verified)
        self.assertTrue(SecurityEvent.objects.filter(user=self.user, event_type="email_changed").exists())
        self.client.logout()
        self.login("NEW.PERSON@example.com")
        self.assertTrue(self.signed_in())

    def test_it_needs_the_current_password(self):
        r = self.save("x@example.com", "wrong")
        self.assertContains(r, "That password is not correct")
        self.user.refresh_from_db(); self.assertIsNone(self.user.email)

    def test_wrong_passwords_here_count_towards_the_account_lockout(self):
        for _ in range(5):
            self.save("x@example.com", "wrong")
        r = self.save("x@example.com", PASSWORD)                                # even the right password is refused now
        self.assertContains(r, "Too many wrong passwords")
        self.user.refresh_from_db(); self.assertIsNone(self.user.email)
        self.client.logout()
        self.assertContains(self.login("0772100001"), "Too many failed attempts")   # and the login page agrees

    def test_an_email_used_by_someone_else_cannot_be_taken(self):
        self.member(phone="+256772100002", email="taken@example.com")
        for spelling in ("taken@example.com", "TAKEN@Example.com"):
            self.assertContains(self.save(spelling), "already used by another account")
        self.user.refresh_from_db(); self.assertIsNone(self.user.email)

    def test_saving_your_own_email_again_is_fine(self):
        self.save("mine@example.com")
        self.assertRedirects(self.save("Mine@example.com"), self.URL, fetch_redirect_response=False)

    def test_a_malformed_email_is_refused(self):
        self.assertContains(self.save("not-an-email"), "Enter a valid email")

    def test_an_email_can_be_removed_and_the_phone_keeps_working(self):
        self.save("gone@example.com")
        self.save("")
        self.user.refresh_from_db(); self.assertIsNone(self.user.email)
        self.client.logout()
        self.login("gone@example.com"); self.assertFalse(self.signed_in())
        self.login("0772100001"); self.assertTrue(self.signed_in())

    def test_a_long_email_can_be_saved(self):
        self.save(LONG)
        self.user.refresh_from_db(); self.assertEqual(self.user.email, LONG)

    def test_the_dashboard_header_links_to_it(self):
        from members.models import Member
        Member.objects.create(user=self.user, area=self.area)
        self.assertIn(self.URL, self.client.get(reverse("member")).content.decode())

    def test_switch_role_still_requires_a_login(self):
        self.client.logout()
        r = self.client.post(reverse("accounts:switch_role"), {"role": "member"})
        self.assertEqual(r.status_code, 302)
        self.assertIn("/accounts/login", r["Location"])


class SignupEmailTests(Base):
    def register(self, phone, email=""):
        with patch("accounts.views._send_otp_dev"):
            return self.client.post(reverse("accounts:register"), {
                "phone": phone, "email": email, "password": PASSWORD, "password_confirm": PASSWORD, "area": self.area.pk})

    def test_people_can_sign_up_without_an_email_any_number_of_times(self):
        for i, phone in enumerate(("0772300001", "0772300002", "0772300003")):
            self.client.logout()
            self.assertEqual(self.register(phone).status_code, 302, phone)
        self.assertEqual(User.objects.filter(email__isnull=True).count(), 3)       # NULL, not "": the column is unique

    def test_an_email_given_at_signup_is_stored_in_one_spelling_and_works_after_verifying(self):
        sent = []
        with patch("accounts.views._send_otp_dev", side_effect=lambda u, otp, p: sent.append(otp)):
            self.client.post(reverse("accounts:register"), {
                "phone": "0772300009", "email": " Mixed.Case@Example.COM ", "password": PASSWORD,
                "password_confirm": PASSWORD, "area": self.area.pk})
        self.assertEqual(User.objects.get(phone="+256772300009").email, "mixed.case@example.com")
        self.client.post(reverse("accounts:verify_phone"), {"code": sent[0]})
        self.client.logout()
        self.login("MIXED.case@example.com")
        self.assertTrue(self.signed_in())

    def test_the_same_email_in_another_case_is_a_duplicate(self):
        self.register("0772300004", "dup@example.com")
        self.client.logout()
        r = self.register("0772300005", "DUP@example.com")
        self.assertContains(r, "An account with this email already exists")

    def test_the_signup_page_explains_the_email_option(self):
        html = self.client.get(reverse("accounts:register")).content.decode()
        self.assertIn("sign in with either your phone number or your email", html)
