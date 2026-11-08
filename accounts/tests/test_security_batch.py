"""Account security: (1) an unverified phone can never sign in, (2) one SIM = one account whatever its spelling,
(3) failed-login counters can't be dodged by changing spelling/case, (4) one address can't stuff credentials,
(5) super admins still get every profile (a deliberate design that must not regress)."""
import importlib
from datetime import timedelta
from unittest.mock import patch

from django.apps import apps as real_apps
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.forms import RegisterForm
from accounts.models import LoginAttempt, PhoneVerification, Role, User, UserRole
from accounts.phone import canonical_identifier, canonical_phone, phone_variants
from core.models import Area, SystemSetting

PASSWORD = "Pass12345!x"


class Base(TestCase):
    def setUp(self):
        cache.clear()
        self.area = Area.objects.create(name="Kireka", latitude=0.3464, longitude=32.6475)

    def login(self, identifier, password=PASSWORD, **extra):
        return self.client.post(reverse("accounts:login"), {"identifier": identifier, "password": password}, **extra)

    def signed_in(self):
        return "_auth_user_id" in self.client.session


# ====================================================================== unverified phones must verify first ============
class UnverifiedMustVerifyTests(Base):
    """The rule: a person whose phone number has not been verified cannot sign in. Correct password only leads to the
    verification page; no session exists until the code is accepted."""

    def make(self, role=Role.MEMBER, phone="+256772100001", **kw):
        return User.objects.create_user(phone=phone, email=kw.pop("email", None), password=PASSWORD, role=role,
                                        phone_verified=False, **kw)

    def test_correct_password_does_not_sign_an_unverified_member_in(self):
        self.make()
        r = self.login("+256772100001")
        self.assertRedirects(r, reverse("accounts:verify_phone"), fetch_redirect_response=False)
        self.assertFalse(self.signed_in())
        self.assertIn("pending_verify_user_id", self.client.session)

    def test_unverified_cannot_reach_any_dashboard(self):
        self.make()
        self.login("+256772100001")
        for name in ("member", "merchant", "rider"):
            r = self.client.get(reverse(name))
            self.assertEqual(r.status_code, 302, name)
            self.assertIn("/accounts/login", r["Location"], name)

    def test_same_rule_for_merchants_riders_and_agents(self):
        for i, role in enumerate([Role.MERCHANT, Role.RIDER, Role.AGENT]):
            self.client.logout()
            phone = f"+25677210{i + 2:04d}"
            self.make(role=role, phone=phone)
            r = self.login(phone)
            self.assertRedirects(r, reverse("accounts:verify_phone"), fetch_redirect_response=False)
            self.assertFalse(self.signed_in(), role)

    def test_any_spelling_of_the_phone_still_has_to_verify(self):
        self.make()
        for spelling in ("0772100001", "772100001", "0772 100 001", "+256 772 100 001"):
            self.client.logout()
            r = self.login(spelling)
            self.assertRedirects(r, reverse("accounts:verify_phone"), fetch_redirect_response=False)
            self.assertFalse(self.signed_in(), spelling)

    def test_email_login_of_an_unverified_member_also_has_to_verify(self):
        self.make(email="new@example.com")
        r = self.login("NEW@example.com")
        self.assertRedirects(r, reverse("accounts:verify_phone"), fetch_redirect_response=False)
        self.assertFalse(self.signed_in())

    def test_wrong_password_reveals_nothing_and_starts_no_verification(self):
        self.make()
        r = self.login("+256772100001", "wrong-password")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Invalid credentials")
        self.assertNotIn("pending_verify_user_id", self.client.session)

    def test_a_wrong_code_does_not_sign_in_and_five_wrong_guesses_burn_the_code(self):
        user = self.make()
        _, code = PhoneVerification.issue(user, PhoneVerification.Purpose.REGISTRATION)
        self.login("+256772100001")
        for _ in range(5):
            r = self.client.post(reverse("accounts:verify_phone"), {"code": "000000" if code != "000000" else "111111"})
            self.assertContains(r, "Invalid or expired code")
        self.assertFalse(self.signed_in())
        r = self.client.post(reverse("accounts:verify_phone"), {"code": code})      # even the RIGHT code is now refused
        self.assertContains(r, "Invalid or expired code")
        self.assertFalse(self.signed_in())
        user.refresh_from_db(); self.assertFalse(user.phone_verified)

    def test_an_expired_code_does_not_sign_in(self):
        user = self.make()
        v, code = PhoneVerification.issue(user, PhoneVerification.Purpose.REGISTRATION)
        PhoneVerification.objects.filter(pk=v.pk).update(expires_at=timezone.now() - timedelta(minutes=1))
        self.login("+256772100001")
        r = self.client.post(reverse("accounts:verify_phone"), {"code": code})
        self.assertContains(r, "Invalid or expired code")
        self.assertFalse(self.signed_in())

    def test_a_withdrawal_code_can_never_verify_a_phone(self):
        user = self.make()
        _, wcode = PhoneVerification.issue(user, PhoneVerification.Purpose.WITHDRAWAL)
        self.login("+256772100001")
        r = self.client.post(reverse("accounts:verify_phone"), {"code": wcode})
        self.assertContains(r, "Invalid or expired code")
        self.assertFalse(self.signed_in())
        user.refresh_from_db(); self.assertFalse(user.phone_verified)

    def test_the_right_code_verifies_then_signs_in(self):
        user = self.make()
        _, code = PhoneVerification.issue(user, PhoneVerification.Purpose.REGISTRATION)
        self.login("+256772100001")
        r = self.client.post(reverse("accounts:verify_phone"), {"code": code})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(self.signed_in())
        user.refresh_from_db(); self.assertTrue(user.phone_verified)
        self.assertNotIn("pending_verify_user_id", self.client.session)

    def test_registration_signs_nobody_in_it_only_starts_verification(self):
        sent = []
        with patch("accounts.views._send_otp_dev", side_effect=lambda u, otp, p: sent.append(otp)):
            r = self.client.post(reverse("accounts:register"), {
                "phone": "0772 200 002", "password": PASSWORD, "password_confirm": PASSWORD, "area": self.area.pk})
        self.assertRedirects(r, reverse("accounts:verify_phone"), fetch_redirect_response=False)
        self.assertFalse(self.signed_in())
        self.assertEqual(len(sent), 1)
        user = User.objects.get(phone="+256772200002")
        self.assertFalse(user.phone_verified)
        # and the new member cannot sign in until they use that code
        self.client.logout()
        self.assertFalse(self.login("0772200002").url.startswith("/member") if self.login("0772200002").status_code == 302 else False)
        self.assertFalse(self.signed_in())
        self.client.post(reverse("accounts:verify_phone"), {"code": sent[0]})
        self.assertTrue(self.signed_in())

    def test_verified_members_sign_in_normally(self):
        User.objects.create_user(phone="+256772100077", password=PASSWORD, role=Role.MEMBER, phone_verified=True)
        r = self.login("0772100077")
        self.assertEqual(r.status_code, 302)
        self.assertTrue(self.signed_in())


# ====================================================================== admins keep their special treatment ============
@override_settings(AUTO_CREATE_ADMIN_PROFILES=True)      # the test settings switch it off globally; production has it on
class AdminBehaviourUnchangedTests(Base):
    def test_super_admin_gets_every_profile_when_created(self):
        from agents.models import Agent
        from members.models import Member
        from merchants.models import Merchant
        from riders.models import Rider

        admin = User.objects.create_superuser(phone="+256772300001", password=PASSWORD)
        for model in (Member, Merchant, Rider, Agent):
            self.assertTrue(model.objects.filter(user=admin).exists(), model.__name__)

    def test_admin_can_sign_in_without_phone_verification(self):
        User.objects.create_superuser(phone="+256772300002", password=PASSWORD)
        self.login("+256772300002")
        self.assertTrue(self.signed_in())


# ====================================================================== one SIM, one account ==========================
class CanonicalPhoneTests(Base):
    def test_every_spelling_has_one_canonical_form(self):
        for raw in ("0772123456", "+256772123456", "256772123456", "772123456", "0772 123 456", "+256 (772) 123-456"):
            self.assertEqual(canonical_phone(raw), "+256772123456", raw)

    def test_rejects_things_that_are_not_ugandan_mobiles(self):
        for raw in ("", None, "abc", "12345", "+254712345678", "0412345678", "07721234", "+2567721234567", "0872123456"):
            self.assertIsNone(canonical_phone(raw), raw)

    def test_agrees_with_the_payments_normaliser(self):
        from payments.config import normalize_msisdn

        for raw in ("0772123456", "+256772123456", "772123456", "0412345678", "abc"):
            n = normalize_msisdn(raw)
            self.assertEqual(canonical_phone(raw), ("+" + n) if n else None, raw)

    def test_identifier_canonicalisation(self):
        self.assertEqual(canonical_identifier("  Name@Example.COM "), "name@example.com")
        self.assertEqual(canonical_identifier("0772123456"), "+256772123456")

    def test_variants_cover_legacy_spellings(self):
        self.assertEqual(phone_variants("0772123456"), ["+256772123456", "256772123456", "0772123456", "772123456"])
        self.assertEqual(phone_variants("nope"), [])

    # -- registration form
    def reg(self, phone, **extra):
        data = {"phone": phone, "password": PASSWORD, "password_confirm": PASSWORD, "area": self.area.pk, **extra}
        return RegisterForm(data)

    def test_registration_stores_the_canonical_number(self):
        f = self.reg("0772 123 456")
        self.assertTrue(f.is_valid(), f.errors)
        self.assertEqual(f.cleaned_data["phone"], "+256772123456")

    def test_registration_rejects_junk_numbers_with_a_helpful_message(self):
        for bad in ("abc", "12345", "+254712345678", "0412345678"):
            f = self.reg(bad)
            self.assertFalse(f.is_valid(), bad)
            self.assertIn("valid Ugandan mobile number", str(f.errors["phone"]), bad)

    def test_a_second_spelling_of_a_taken_number_is_a_duplicate(self):
        User.objects.create_user(phone="+256772123456", password=PASSWORD, role=Role.MEMBER, phone_verified=True)
        for spelling in ("0772123456", "772123456", "+256 772 123 456"):
            f = self.reg(spelling)
            self.assertFalse(f.is_valid(), spelling)
            self.assertIn("already exists", str(f.errors["phone"]))

    def test_a_legacy_row_stored_the_old_way_still_blocks_a_duplicate(self):
        User.objects.create_user(phone="0772123456", password=PASSWORD, role=Role.MEMBER, phone_verified=True)
        f = self.reg("+256772123456")
        self.assertFalse(f.is_valid())

    def test_a_stale_unverified_squatter_is_released_under_any_spelling(self):
        squatter = User.objects.create_user(phone="0772123456", password=PASSWORD, role=Role.MEMBER)
        User.objects.filter(pk=squatter.pk).update(date_joined=timezone.now() - timedelta(days=3))
        sent = []
        with patch("accounts.views._send_otp_dev", side_effect=lambda u, otp, p: sent.append(otp)):
            r = self.client.post(reverse("accounts:register"), {
                "phone": "+256772123456", "password": PASSWORD, "password_confirm": PASSWORD, "area": self.area.pk})
        self.assertEqual(r.status_code, 302)
        self.assertFalse(User.objects.filter(pk=squatter.pk).exists())
        self.assertEqual(User.objects.filter(phone="+256772123456").count(), 1)

    # -- login by any spelling
    def test_login_accepts_every_spelling(self):
        User.objects.create_user(phone="+256772123456", password=PASSWORD, role=Role.MEMBER, phone_verified=True)
        for spelling in ("0772123456", "772123456", "+256 772 123 456", "256772123456"):
            self.client.logout()
            self.login(spelling)
            self.assertTrue(self.signed_in(), spelling)

    def test_login_finds_an_account_stored_the_old_way(self):
        User.objects.create_user(phone="0772123456", password=PASSWORD, role=Role.MEMBER, phone_verified=True)
        self.login("+256772123456")
        self.assertTrue(self.signed_in())

    def test_email_login_is_case_insensitive(self):
        User.objects.create_user(phone="+256772123456", email="Jane@Example.com", password=PASSWORD,
                                 role=Role.MEMBER, phone_verified=True)
        self.login("jane@EXAMPLE.com")
        self.assertTrue(self.signed_in())

    # -- the data migration
    def test_migration_rewrites_only_unambiguous_numbers(self):
        mod = importlib.import_module("accounts.migrations.0007_canonical_phones")
        solo = User.objects.create_user(phone="0772000001", password="x", role=Role.MEMBER)
        ok = User.objects.create_user(phone="+256772000002", password="x", role=Role.MEMBER)
        dup_a = User.objects.create_user(phone="0772000003", password="x", role=Role.MEMBER)
        dup_b = User.objects.create_user(phone="772000003", password="x", role=Role.MEMBER)
        odd = User.objects.create_user(phone="+254700000009", password="x", role=Role.MEMBER)
        mod.canonicalise(real_apps, None)
        for u in (solo, ok, dup_a, dup_b, odd):
            u.refresh_from_db()
        self.assertEqual(solo.phone, "+256772000001")          # rewritten
        self.assertEqual(ok.phone, "+256772000002")            # already canonical
        self.assertEqual((dup_a.phone, dup_b.phone), ("0772000003", "772000003"))   # ambiguous: left for a human
        self.assertEqual(odd.phone, "+254700000009")           # not Ugandan: untouched
        mod.canonicalise(real_apps, None)                      # idempotent
        solo.refresh_from_db(); self.assertEqual(solo.phone, "+256772000001")


# ====================================================================== lockout can't be dodged =======================
class LockoutTests(Base):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(phone="+256772400001", email="Victim@Example.com", password=PASSWORD,
                                             role=Role.MEMBER, phone_verified=True)

    def locked(self, response):
        return "Too many failed attempts" in response.content.decode()

    def test_changing_email_letter_case_does_not_give_fresh_guesses(self):
        variants = ["victim@example.com", "Victim@example.com", "VICTIM@example.com", "vIctim@example.com",
                    "viCtim@example.com", "vicTim@example.com", "victIm@example.com", "victiM@example.com"]
        results = [self.locked(self.login(v, "wrong")) for v in variants]
        self.assertEqual(results, [False] * 5 + [True] * 3)       # 5 guesses TOTAL, however it is spelled

    def test_changing_the_phone_spelling_does_not_give_fresh_guesses(self):
        spellings = ["+256772400001", "0772400001", "772400001", "0772 400 001", "256772400001", "+256 772 400 001"]
        results = [self.locked(self.login(s, "wrong")) for s in spellings]
        self.assertEqual(results, [False] * 5 + [True])

    def test_mixed_email_and_phone_are_separate_identities_as_before(self):
        for _ in range(5):
            self.login("+256772400001", "wrong")
        self.assertTrue(self.locked(self.login("+256772400001", PASSWORD)))      # locked even with the right password
        self.assertFalse(self.locked(self.login("victim@example.com", "wrong")))  # the email identity is counted separately

    def test_correct_password_works_until_the_threshold(self):
        for _ in range(4):
            self.login("0772400001", "wrong")
        self.login("0772400001", PASSWORD)
        self.assertTrue(self.signed_in())

    def test_recent_failures_counts_any_spelling_directly(self):
        for ident in ("+256772400001", "0772400001"):
            LoginAttempt.objects.create(identifier=canonical_identifier(ident), success=False)
        self.assertEqual(LoginAttempt.recent_failures("772400001"), 2)
        self.assertEqual(LoginAttempt.recent_failures("0772400001"), 2)


class IpCeilingTests(Base):
    IP = "10.9.8.7"

    def flood(self, n, ip=None):
        LoginAttempt.objects.bulk_create([
            LoginAttempt(identifier=f"victim{i}@example.com", ip_address=ip or self.IP, success=False) for i in range(n)])

    def setUp(self):
        super().setUp()
        User.objects.create_user(phone="+256772500001", password=PASSWORD, role=Role.MEMBER, phone_verified=True)

    def test_one_address_failing_against_many_accounts_is_paused(self):
        self.flood(40)
        r = self.login("+256772500001", PASSWORD, REMOTE_ADDR=self.IP)           # even the right password
        self.assertContains(r, "Too many failed attempts from your network")
        self.assertFalse(self.signed_in())

    def test_other_addresses_are_unaffected(self):
        self.flood(40)
        self.login("+256772500001", PASSWORD, REMOTE_ADDR="10.1.1.1")
        self.assertTrue(self.signed_in())

    def test_just_under_the_ceiling_is_fine(self):
        self.flood(39)
        self.login("+256772500001", PASSWORD, REMOTE_ADDR=self.IP)
        self.assertTrue(self.signed_in())

    def test_old_failures_age_out(self):
        self.flood(40)
        LoginAttempt.objects.update(created_at=timezone.now() - timedelta(minutes=30))
        self.login("+256772500001", PASSWORD, REMOTE_ADDR=self.IP)
        self.assertTrue(self.signed_in())

    def test_ceiling_is_adjustable_but_never_below_ten(self):
        SystemSetting.objects.update_or_create(key="security.login_ip_failure_limit", defaults={"value": "12"})
        self.flood(12)
        self.assertContains(self.login("+256772500001", PASSWORD, REMOTE_ADDR=self.IP), "from your network")
        SystemSetting.objects.filter(key="security.login_ip_failure_limit").update(value="1")      # silly value is floored
        LoginAttempt.objects.all().delete(); self.flood(9)
        self.login("+256772500001", PASSWORD, REMOTE_ADDR=self.IP)
        self.assertTrue(self.signed_in())
