from django.test import TestCase

from accounts.models import User
from core.models import Area
from members.models import Member


class MemberModelTests(TestCase):
    def test_member_gets_unique_referral_code(self):
        area = Area.objects.create(name="Testville")
        user1 = User.objects.create_user(phone="+256700920001", password="pass12345")
        user2 = User.objects.create_user(phone="+256700920002", password="pass12345")
        m1 = Member.objects.create(user=user1, area=area)
        m2 = Member.objects.create(user=user2, area=area, referred_by=m1)
        self.assertNotEqual(m1.referral_code, m2.referral_code)
        self.assertEqual(m2.referred_by, m1)
