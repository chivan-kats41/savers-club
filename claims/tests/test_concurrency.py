import threading

from django.db import OperationalError, connections
from django.test import TransactionTestCase
from django.utils import timezone
from datetime import timedelta

from accounts.models import Role, User
from claims.services import ClaimError, claim_offer
from core.models import Area
from members.models import Member
from merchants.models import Merchant
from offers.models import Offer, OfferCategory


class ConcurrentClaimTests(TransactionTestCase):
    """select_for_update() on the offer row must prevent two members from
    both claiming the last unit of stock.

    NOTE: SQLite (used here for tests) has no real row-level locking —
    select_for_update() degrades to whole-table locking, and a losing
    writer can surface as OperationalError("database table is locked")
    rather than blocking and then cleanly failing with ClaimError. Both
    outcomes count as "this claim did not go through" for this test.
    Under MySQL/Postgres in production, select_for_update() gives true
    row-level blocking and every loser resolves to a clean ClaimError.
    """

    def test_only_one_claim_succeeds_for_last_unit(self):
        area = Area.objects.create(name="Testville")
        category = OfferCategory.objects.create(key="soap", label="Soap")
        m_user = User.objects.create_user(phone="+256700970000", password="pass12345", role=Role.MERCHANT)
        merchant = Merchant.objects.create(user=m_user, business_name="Test Shop", category=category, area=area)
        offer = Offer.objects.create(
            merchant=merchant, category=category, area=area, item_name="Last unit",
            normal_price=3000, member_price=2500, quantity=1,
            expires_at=timezone.now() + timedelta(days=1), status=Offer.Status.ACTIVE,
        )

        members = []
        for i in range(5):
            u = User.objects.create_user(phone=f"+25670097100{i}", password="pass12345", role=Role.MEMBER)
            members.append(Member.objects.create(user=u, area=area))

        results = []

        def attempt(member):
            try:
                claim_offer(member, offer.id)
                results.append("ok")
            except (ClaimError, OperationalError):
                results.append("failed")
            finally:
                connections.close_all()

        threads = [threading.Thread(target=attempt, args=(m,)) for m in members]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(results.count("ok"), 1, f"exactly one claim should succeed, got: {results}")
        self.assertEqual(results.count("failed"), 4)
        offer.refresh_from_db()
        self.assertEqual(offer.quantity, 0)
