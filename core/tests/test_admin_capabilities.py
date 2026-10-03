from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from accounts.models import Role, User
from core.models import Area, AuditLog


class UserSuspensionTests(TestCase):
    def setUp(self):
        self.target = User.objects.create_user(phone="+256701600000", password="pass12345", role=Role.MEMBER)

    def test_plain_admin_without_capability_forbidden(self):
        admin_user = User.objects.create_user(phone="+256701600001", password="pass12345", role=Role.ADMIN)
        self.client.force_login(admin_user)
        resp = self.client.post(reverse("accounts_api:suspend_user", args=[self.target.id]))
        self.assertEqual(resp.status_code, 403)

    def test_admin_with_capability_can_suspend(self):
        admin_user = User.objects.create_user(phone="+256701600002", password="pass12345", role=Role.ADMIN)
        perm = Permission.objects.get(content_type__app_label="core", codename="users_suspend")
        admin_user.user_permissions.add(perm)
        self.client.force_login(admin_user)

        resp = self.client.post(reverse("accounts_api:suspend_user", args=[self.target.id]))
        self.assertEqual(resp.status_code, 200)
        self.target.refresh_from_db()
        self.assertFalse(self.target.is_active)
        self.assertTrue(AuditLog.objects.filter(action="user_suspended", object_id=str(self.target.id)).exists())

    def test_superuser_bypasses_capability_check(self):
        super_user = User.objects.create_superuser(phone="+256701600003", password="pass12345")
        self.client.force_login(super_user)
        resp = self.client.post(reverse("accounts_api:suspend_user", args=[self.target.id]))
        self.assertEqual(resp.status_code, 200)

    def test_cannot_suspend_superuser_without_being_one(self):
        super_target = User.objects.create_superuser(phone="+256701600004", password="pass12345")
        admin_user = User.objects.create_user(phone="+256701600005", password="pass12345", role=Role.ADMIN)
        perm = Permission.objects.get(content_type__app_label="core", codename="users_suspend")
        admin_user.user_permissions.add(perm)
        self.client.force_login(admin_user)

        resp = self.client.post(reverse("accounts_api:suspend_user", args=[super_target.id]))
        self.assertEqual(resp.status_code, 403)
        super_target.refresh_from_db()
        self.assertTrue(super_target.is_active)

    def test_reactivate(self):
        self.target.is_active = False
        self.target.save()
        super_user = User.objects.create_superuser(phone="+256701600006", password="pass12345")
        self.client.force_login(super_user)
        resp = self.client.post(reverse("accounts_api:reactivate_user", args=[self.target.id]))
        self.assertEqual(resp.status_code, 200)
        self.target.refresh_from_db()
        self.assertTrue(self.target.is_active)


class AdminReportsTests(TestCase):
    def test_requires_capability(self):
        admin_user = User.objects.create_user(phone="+256701610000", password="pass12345", role=Role.ADMIN)
        self.client.force_login(admin_user)
        resp = self.client.get(reverse("core_api:admin_reports_summary"))
        self.assertEqual(resp.status_code, 403)

    def test_superuser_can_view_reports(self):
        super_user = User.objects.create_superuser(phone="+256701610001", password="pass12345")
        self.client.force_login(super_user)
        resp = self.client.get(reverse("core_api:admin_reports_summary"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("members_total", resp.json()["data"])

    def test_member_forbidden(self):
        member_user = User.objects.create_user(phone="+256701610002", password="pass12345", role=Role.MEMBER)
        self.client.force_login(member_user)
        resp = self.client.get(reverse("core_api:admin_reports_summary"))
        self.assertEqual(resp.status_code, 403)
