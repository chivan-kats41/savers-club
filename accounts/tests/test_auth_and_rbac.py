from unittest.mock import patch
from django.test import TestCase
from django.urls import reverse

from accounts.models import PhoneVerification, Role, User, UserRole
from core.models import Area
from members.models import Member


class RegistrationAndVerificationTests(TestCase):
    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        self.area = Area.objects.create(name="Testville")

    def test_register_then_verify_logs_in(self):
        with patch("accounts.models.secrets.randbelow", return_value=123456):   # pin the 6-digit code
            resp = self.client.post(
                reverse("accounts:register"),
                {
                    "phone": "+256700111222",
                    "email": "new@example.com",
                    "first_name": "Test",
                    "last_name": "User",
                    "area": self.area.id,
                    "password": "StrongPass123!",
                    "password_confirm": "StrongPass123!",
                },
            )
        self.assertRedirects(resp, reverse("accounts:verify_phone"))
        user = User.objects.get(phone="+256700111222")
        self.assertFalse(user.phone_verified)
        self.assertTrue(UserRole.objects.filter(user=user, role=Role.MEMBER).exists())
        self.assertTrue(Member.objects.filter(user=user, area=self.area).exists())

        raw_code = "123456"

        resp = self.client.post(reverse("accounts:verify_phone"), {"code": raw_code})
        self.assertRedirects(resp, reverse("member"))
        user.refresh_from_db()
        self.assertTrue(user.phone_verified)

    def test_duplicate_phone_rejected(self):
        User.objects.create_user(phone="+256700000001", password="pass12345")
        resp = self.client.post(
            reverse("accounts:register"),
            {
                "phone": "+256700000001",
                "password": "StrongPass123!",
                "password_confirm": "StrongPass123!",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "already exists")


class LoginLockoutTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            phone="+256700333444", email="lock@example.com", password="CorrectPass1!", phone_verified=True
        )

    def test_wrong_password_fails(self):
        resp = self.client.post(
            reverse("accounts:login"), {"identifier": "+256700333444", "password": "wrong"}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Invalid credentials")

    def test_login_by_email_works(self):
        resp = self.client.post(
            reverse("accounts:login"), {"identifier": "lock@example.com", "password": "CorrectPass1!"}
        )
        self.assertRedirects(resp, reverse("member"))

    def test_lockout_after_five_failures(self):
        for _ in range(5):
            self.client.post(
                reverse("accounts:login"), {"identifier": "+256700333444", "password": "wrong"}
            )
        resp = self.client.post(
            reverse("accounts:login"), {"identifier": "+256700333444", "password": "CorrectPass1!"}
        )
        self.assertContains(resp, "Too many failed attempts")


class RoleGatingTests(TestCase):
    def setUp(self):
        self.member = User.objects.create_user(
            phone="+256700555000", password="pass12345", role=Role.MEMBER
        )
        self.merchant = User.objects.create_user(
            phone="+256700555001", password="pass12345", role=Role.MERCHANT
        )
        self.admin = User.objects.create_user(
            phone="+256700555002", password="pass12345", role=Role.ADMIN
        )

    def test_anonymous_redirected_to_login(self):
        resp = self.client.get(reverse("member"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("accounts:login"), resp.url)

    def test_member_cannot_reach_merchant_dashboard(self):
        self.client.force_login(self.member)
        resp = self.client.get(reverse("merchant"))
        self.assertEqual(resp.status_code, 403)

    def test_member_reaches_own_dashboard(self):
        self.client.force_login(self.member)
        resp = self.client.get(reverse("member"))
        self.assertEqual(resp.status_code, 200)

    def test_non_admin_cannot_reach_admin_console(self):
        self.client.force_login(self.member)
        resp = self.client.get(reverse("admin_index"))
        self.assertEqual(resp.status_code, 403)

    def test_admin_reaches_admin_console(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("admin_index"))
        self.assertEqual(resp.status_code, 200)

    def test_landing_stays_public(self):
        resp = self.client.get(reverse("landing"))
        self.assertEqual(resp.status_code, 200)


class RoleSwitchTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            phone="+256700666000", password="pass12345", role=Role.MEMBER
        )
        UserRole.objects.create(user=self.user, role=Role.MEMBER)
        UserRole.objects.create(user=self.user, role=Role.RIDER)

    def test_switch_to_assigned_role_succeeds(self):
        self.client.force_login(self.user)
        resp = self.client.post(reverse("accounts:switch_role"), {"role": "rider"})
        self.assertRedirects(resp, reverse("rider"))
        self.user.refresh_from_db()
        self.assertEqual(self.user.role, "rider")

    def test_switch_to_unassigned_role_rejected(self):
        self.client.force_login(self.user)
        resp = self.client.post(reverse("accounts:switch_role"), {"role": "agent"})
        self.user.refresh_from_db()
        self.assertEqual(self.user.role, "member")
