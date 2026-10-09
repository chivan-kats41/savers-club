"""Super admins automatically get a member, merchant, rider and agent profile (accounts/admin_profiles.py)."""
import json
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.admin_profiles import ensure_admin_profiles, is_super_admin
from accounts.models import Role, User, UserRole
from agents.models import Agent
from core.models import Area
from members.models import Member
from merchants.models import Merchant, MerchantVerification
from offers.models import Offer, OfferCategory
from riders.models import Rider, RiderVerification

ON = override_settings(AUTO_CREATE_ADMIN_PROFILES=True)


def world():
    """Areas + a category: what `migrate` + `seed_reference_data` provide in a real install."""
    a = Area.objects.create(name="Mbarara", is_launch_area=True)
    b = Area.objects.create(name="Kampala Central", is_launch_area=False)
    cat = OfferCategory.objects.create(key="general", label="General Shop", emoji="🏪")
    return a, b, cat


@ON
class CreationTests(TestCase):
    def test_create_superuser_gets_all_four_profiles_with_correct_state(self):
        area, other, cat = world()
        u = User.objects.create_superuser(phone="+256762899642", password="pass12345")
        self.assertTrue(Member.objects.filter(user=u, area=area).exists())          # launch area preferred
        m = Merchant.objects.get(user=u)
        self.assertEqual((m.status, m.verified_by, m.category), (Merchant.Status.VERIFIED, u, cat))
        r = Rider.objects.get(user=u)
        self.assertEqual((r.status, r.verified_by), (Rider.Status.VERIFIED, u))
        self.assertFalse(r.is_available)                                           # not an "available boda" for real jobs
        agent = Agent.objects.get(user=u)
        self.assertEqual(agent.status, Agent.Status.ACTIVE)
        self.assertEqual(set(agent.areas.values_list("pk", flat=True)), {area.pk, other.pk})   # every active area
        self.assertEqual(set(u.assigned_roles.filter(is_active=True).values_list("role", flat=True)),
                         {"member", "merchant", "rider", "agent"})
        # audit trail explains where the verified profiles came from
        self.assertTrue(MerchantVerification.objects.filter(merchant=m, performed_by=u, checklist__auto_created_for_super_admin=True).exists())
        self.assertTrue(RiderVerification.objects.filter(rider=r, performed_by=u).exists())

    def test_promoting_an_existing_user_creates_profiles(self):
        world()
        u = User.objects.create_user(phone="+256700000020", password="x", role=Role.MEMBER)
        self.assertFalse(Merchant.objects.filter(user=u).exists())
        u.is_superuser = True
        u.save()
        self.assertTrue(Merchant.objects.filter(user=u).exists() and Rider.objects.filter(user=u).exists())
        u2 = User.objects.create_user(phone="+256700000021", password="x", role=Role.MEMBER)
        u2.role = Role.SUPER_ADMIN
        u2.save(update_fields=["role"])
        self.assertTrue(Agent.objects.filter(user=u2).exists())

    def test_only_super_admins_get_profiles(self):
        world()
        staff = User.objects.create_user(phone="+256700000022", password="x", role=Role.ADMIN, is_staff=True)
        member = User.objects.create_user(phone="+256700000023", password="x", role=Role.MEMBER)
        for user in (staff, member):
            ensure_admin_profiles(user)
            self.assertFalse(is_super_admin(user))
            self.assertEqual(Merchant.objects.filter(user=user).count() + Rider.objects.filter(user=user).count()
                             + Agent.objects.filter(user=user).count() + Member.objects.filter(user=user).count(), 0)

    def test_idempotent_and_never_overwrites_existing_profiles(self):
        area, other, cat = world()
        u = User.objects.create_superuser(phone="+256762899643", password="pass12345")
        Merchant.objects.filter(user=u).update(status=Merchant.Status.SUSPENDED, business_name="My real shop")
        Member.objects.filter(user=u).update(area=other)
        for _ in range(3):
            ensure_admin_profiles(u)
        for model in (Member, Merchant, Rider, Agent):
            self.assertEqual(model.objects.filter(user=u).count(), 1, model.__name__)
        m = Merchant.objects.get(user=u)
        self.assertEqual((m.status, m.business_name), (Merchant.Status.SUSPENDED, "My real shop"))   # untouched
        self.assertEqual(Member.objects.get(user=u).area, other)
        self.assertEqual(UserRole.objects.filter(user=u).count(), 4)

    @override_settings(AUTO_CREATE_ADMIN_PROFILES=False)
    def test_can_be_switched_off(self):
        world()
        u = User.objects.create_superuser(phone="+256762899644", password="pass12345")
        self.assertFalse(Member.objects.filter(user=u).exists())


@ON
class MissingPrerequisitesTests(TestCase):
    def test_empty_database_still_gets_every_profile_including_merchant(self):
        """No areas, no offer categories, nothing seeded: the merchant profile (and the rest) must still be created."""
        self.assertEqual((Area.objects.count(), OfferCategory.objects.count()), (0, 0))
        u = User.objects.create_superuser(phone="+256762899645", password="pass12345")
        for model in (Member, Merchant, Rider, Agent):
            self.assertTrue(model.objects.filter(user=u).exists(), model.__name__)
        self.assertEqual(Merchant.objects.get(user=u).status, Merchant.Status.VERIFIED)
        self.assertEqual(OfferCategory.objects.filter(key="general").count(), 1)       # created for the merchant
        self.assertEqual(Area.objects.filter(name="Default Area").count(), 1)
        self.assertEqual(ensure_admin_profiles(u).created, [])                          # and nothing is duplicated
        self.assertEqual((Area.objects.count(), OfferCategory.objects.count()), (1, 1))

    def test_merchant_is_created_when_only_inactive_categories_exist(self):
        Area.objects.create(name="A1")
        OfferCategory.objects.create(key="old", label="Old", is_active=False)
        u = User.objects.create_superuser(phone="+256762899654", password="pass12345")
        self.assertTrue(Merchant.objects.filter(user=u).exists())
        self.assertEqual(OfferCategory.objects.count(), 1)                              # reused, not duplicated

    def test_existing_admin_with_no_merchant_gets_one_on_next_login(self):
        """The reported case: the other profiles exist but the merchant one is missing."""
        world()
        u = User.objects.create_superuser(phone="+256762899655", password="pass12345")
        Merchant.objects.filter(user=u).delete()
        self.assertFalse(Merchant.objects.filter(user=u).exists())
        r = self.client.post(reverse("accounts:login"), {"identifier": "+256762899655", "password": "pass12345"})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(Merchant.objects.filter(user=u).exists())

    def test_seeding_categories_later_does_not_duplicate_the_auto_created_one(self):
        from django.core.management import call_command
        Area.objects.create(name="A1")
        User.objects.create_superuser(phone="+256762899656", password="pass12345")      # auto-creates "general"
        call_command("seed_reference_data", verbosity=0)
        self.assertEqual(OfferCategory.objects.filter(key="general").count(), 1)

    def test_one_failing_profile_never_blocks_the_others_and_is_reported(self):
        world()
        u = User.objects.create_user(phone="+256762899657", password="pass12345", role=Role.SUPER_ADMIN)
        for model in (Member, Merchant, Rider, Agent):
            model.objects.filter(user=u).delete()
        with mock.patch("merchants.models.Merchant.objects.create", side_effect=RuntimeError("boom")):
            r = ensure_admin_profiles(u)
        self.assertIn("merchant", r.skipped)
        self.assertIn("RuntimeError", r.skipped["merchant"])
        for model in (Member, Rider, Agent):                                           # the others were still created
            self.assertTrue(model.objects.filter(user=u).exists(), model.__name__)
        self.assertEqual(ensure_admin_profiles(u).created, ["merchant"])               # next run completes the job

    def test_areas_created_later_are_added_to_the_agent(self):
        world()
        u = User.objects.create_superuser(phone="+256762899646", password="pass12345")
        new = Area.objects.create(name="Brand New Town")
        r = ensure_admin_profiles(u)
        self.assertEqual(r.areas_added, 1)
        self.assertIn(new.pk, Agent.objects.get(user=u).areas.values_list("pk", flat=True))
        self.assertEqual(ensure_admin_profiles(u).areas_added, 0)

    def test_failures_never_break_user_creation_or_login(self):
        world()
        with mock.patch("members.models.Member.objects.create", side_effect=RuntimeError("db hiccup")):
            u = User.objects.create_superuser(phone="+256762899647", password="pass12345")   # must not raise
        self.assertTrue(User.objects.filter(pk=u.pk).exists())

    def test_last_login_saves_do_not_rerun_the_work(self):
        world()
        u = User.objects.create_superuser(phone="+256762899648", password="pass12345")
        with mock.patch("accounts.signals.ensure_admin_profiles") as ensure:
            u.save(update_fields=["last_login"])
            ensure.assert_not_called()
            u.save()                                                   # a normal save does re-check (cheap, idempotent)
            ensure.assert_called_once()

    def test_signing_in_through_the_real_login_page_creates_missing_profiles(self):
        world()
        with override_settings(AUTO_CREATE_ADMIN_PROFILES=False):                      # an admin from before this feature
            u = User.objects.create_superuser(phone="+256762899660", password="pass12345")
        self.assertFalse(Rider.objects.filter(user=u).exists())
        r = self.client.post(reverse("accounts:login"), {"identifier": "+256762899660", "password": "pass12345"})
        self.assertEqual(r.status_code, 302, "login should succeed and redirect")
        for model in (Member, Merchant, Rider, Agent):
            self.assertTrue(model.objects.filter(user=u).exists(), model.__name__)



@ON
class PagesTests(TestCase):
    def setUp(self):
        self.area, self.other, self.cat = world()

    def test_every_role_page_works_for_a_super_admin_even_without_profiles(self):
        # An admin created BEFORE this feature existed: has the user row but no profiles.
        with override_settings(AUTO_CREATE_ADMIN_PROFILES=False):
            u = User.objects.create_superuser(phone="+256762899649", password="pass12345")
        self.assertFalse(Member.objects.filter(user=u).exists())
        self.client.force_login(u)
        for name in ("member", "merchant", "rider", "agent", "admin_index"):
            r = self.client.get(reverse(name), follow=True)
            self.assertEqual(r.status_code, 200, name)
            self.assertNotContains(r, "Your profile isn't set up yet", msg_prefix=name)
        for model in (Member, Merchant, Rider, Agent):
            self.assertTrue(model.objects.filter(user=u).exists(), model.__name__)

    def test_page_explains_why_when_a_profile_genuinely_cannot_be_created(self):
        with override_settings(AUTO_CREATE_ADMIN_PROFILES=False):
            u = User.objects.create_superuser(phone="+256762899650", password="pass12345")
        with mock.patch("merchants.models.Merchant.objects.create", side_effect=RuntimeError("boom")):
            self.client.force_login(u)                      # login itself tries (and fails) to create the merchant
            r = self.client.get(reverse("merchant"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "couldn't create your")
        self.assertContains(r, "RuntimeError")
        r = self.client.get(reverse("merchant"), follow=True)                           # next visit: it just works
        self.assertNotContains(r, "Your profile isn't set up yet")

    def test_regular_users_still_see_the_plain_message_and_get_no_profile(self):
        u = User.objects.create_user(phone="+256700000030", password="x", role=Role.MEMBER)
        self.client.force_login(u)
        r = self.client.get(reverse("member"))
        self.assertContains(r, "Your profile isn't set up yet")
        self.assertFalse(Member.objects.filter(user=u).exists())

    def test_admin_can_actually_use_the_merchant_and_agent_tools(self):
        u = User.objects.create_superuser(phone="+256762899651", password="pass12345")
        self.client.force_login(u)
        payload = {"item_name": "Admin test rice", "category": self.cat.pk, "area": self.area.pk, "normal_price": 20000,
                   "member_price": 18000, "quantity": 5, "expires_at": (timezone.now() + timezone.timedelta(days=2)).isoformat()}
        r = self.client.post("/api/v1/merchant/offers/", json.dumps(payload), content_type="application/json")
        self.assertEqual(r.status_code, 201, r.content)                      # verified merchant: can post
        offer = Offer.objects.get(item_name="Admin test rice")
        r = self.client.post(f"/api/v1/agent/offers/{offer.pk}/approve/")    # and, as agent covering the area, approve it
        self.assertEqual(r.status_code, 200, r.content)
        offer.refresh_from_db()
        self.assertEqual(offer.status, Offer.Status.ACTIVE)
        self.assertEqual({r["role"] for r in self.client.get(reverse("member")).context["all_roles"]},
                         {"member", "merchant", "rider", "agent", "admin"})

    def test_internal_admin_merchant_is_not_counted_in_the_public_seller_number(self):
        before = self.client.get(reverse("landing")).context["stats"]["verified_sellers"]
        User.objects.create_superuser(phone="+256762899652", password="pass12345")
        self.assertEqual(self.client.get(reverse("landing")).context["stats"]["verified_sellers"], before)


@ON
class CommandTests(TestCase):
    def test_command_backfills_existing_super_admins(self):
        world()
        with override_settings(AUTO_CREATE_ADMIN_PROFILES=False):
            u = User.objects.create_superuser(phone="+256762899653", password="pass12345")
        out = StringIO()
        call_command("ensure_admin_profiles", stdout=out)
        text = out.getvalue()
        self.assertIn("+256762899653", text)
        self.assertIn("member", text)
        self.assertTrue(Rider.objects.filter(user=u).exists())
        out = StringIO()
        call_command("ensure_admin_profiles", "+256762899653", stdout=out)
        self.assertIn("created nothing", out.getvalue())                      # second run changes nothing
