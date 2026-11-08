from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from accounts.models import Role, User
from core.models import Area
from item_requests.models import MemberRequest, RequestResponse
from item_requests.services import (
    ItemRequestError,
    cancel_request,
    file_request,
    fulfill_request,
    respond_to_request,
)
from members.models import Member
from merchants.models import Merchant
from offers.models import OfferCategory


class ItemRequestServiceTests(TestCase):
    def setUp(self):
        self.area = Area.objects.create(name="Testville")
        self.category = OfferCategory.objects.create(key="soap", label="Soap")
        mem_user = User.objects.create_user(phone="+256703000000", password="pass12345", role=Role.MEMBER)
        self.member = Member.objects.create(user=mem_user, area=self.area)
        m_user = User.objects.create_user(phone="+256703000001", password="pass12345", role=Role.MERCHANT)
        self.merchant = Merchant.objects.create(
            user=m_user, business_name="Shop", category=self.category, area=self.area,
            status=Merchant.Status.VERIFIED,
        )

    def test_file_request(self):
        req = file_request(self.member, "Phone charger", "Type-C, fast charging", Decimal("15000"))
        self.assertEqual(req.status, MemberRequest.Status.OPEN)
        self.assertEqual(req.area, self.area)

    def test_empty_item_name_rejected(self):
        with self.assertRaises(ItemRequestError):
            file_request(self.member, "")

    def test_negative_budget_rejected(self):
        with self.assertRaises(ItemRequestError):
            file_request(self.member, "Charger", max_budget=Decimal("-100"))

    def test_verified_merchant_can_respond(self):
        req = file_request(self.member, "Phone charger")
        response = respond_to_request(self.merchant, req.id, "I have this in stock", Decimal("12000"))
        req.refresh_from_db()
        self.assertEqual(req.status, MemberRequest.Status.RESPONDED)
        self.assertEqual(response.merchant, self.merchant)

    def test_unverified_merchant_cannot_respond(self):
        u_user = User.objects.create_user(phone="+256703000002", password="pass12345", role=Role.MERCHANT)
        unverified = Merchant.objects.create(user=u_user, business_name="Shop2", category=self.category, area=self.area)
        req = file_request(self.member, "Phone charger")
        with self.assertRaises(ItemRequestError):
            respond_to_request(unverified, req.id)

    def test_merchant_cannot_respond_twice(self):
        req = file_request(self.member, "Phone charger")
        respond_to_request(self.merchant, req.id)
        with self.assertRaises(ItemRequestError):
            respond_to_request(self.merchant, req.id)

    def test_fulfill_with_chosen_response(self):
        req = file_request(self.member, "Phone charger")
        response = respond_to_request(self.merchant, req.id, price=Decimal("12000"))
        fulfilled = fulfill_request(self.member, req.id, response.id)
        self.assertEqual(fulfilled.status, MemberRequest.Status.FULFILLED)
        self.assertEqual(fulfilled.fulfilled_response, response)

    def test_cancel_open_request(self):
        req = file_request(self.member, "Phone charger")
        cancelled = cancel_request(self.member, req.id)
        self.assertEqual(cancelled.status, MemberRequest.Status.CANCELLED)

    def test_cannot_cancel_fulfilled_request(self):
        req = file_request(self.member, "Phone charger")
        fulfill_request(self.member, req.id)
        with self.assertRaises(ItemRequestError):
            cancel_request(self.member, req.id)

    def test_other_member_cannot_fulfill_someone_elses_request(self):
        other_user = User.objects.create_user(phone="+256703000003", password="pass12345", role=Role.MEMBER)
        other_member = Member.objects.create(user=other_user, area=self.area)
        req = file_request(self.member, "Phone charger")
        with self.assertRaises(ItemRequestError):
            fulfill_request(other_member, req.id)


class ItemRequestAPITests(TestCase):
    def setUp(self):
        self.area = Area.objects.create(name="Testville")
        self.category = OfferCategory.objects.create(key="soap", label="Soap")
        mem_user = User.objects.create_user(phone="+256703010000", password="pass12345", role=Role.MEMBER)
        self.member = Member.objects.create(user=mem_user, area=self.area)
        self.member_user = mem_user
        m_user = User.objects.create_user(phone="+256703010001", password="pass12345", role=Role.MERCHANT)
        self.merchant = Merchant.objects.create(
            user=m_user, business_name="Shop", category=self.category, area=self.area,
            status=Merchant.Status.VERIFIED,
        )
        self.merchant_user = m_user

    def test_member_files_request_via_api(self):
        self.client.force_login(self.member_user)
        resp = self.client.post(
            reverse("item_requests:member_requests"),
            {"item_name": "Phone charger", "description": "Type-C", "max_budget": "15000"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 201)

    def test_merchant_sees_open_requests_in_area_and_responds(self):
        req = file_request(self.member, "Phone charger")
        self.client.force_login(self.merchant_user)
        resp = self.client.get(reverse("item_requests:merchant_open_requests"))
        self.assertEqual(len(resp.json()["data"]), 1)

        resp = self.client.post(
            reverse("item_requests:respond_to_request", args=[req.id]),
            {"message": "In stock", "price": "12000"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 201)

    def test_member_sees_responses_on_their_request(self):
        req = file_request(self.member, "Phone charger")
        respond_to_request(self.merchant, req.id, "In stock", Decimal("12000"))
        self.client.force_login(self.member_user)
        resp = self.client.get(reverse("item_requests:member_requests"))
        data = resp.json()["data"][0]
        self.assertEqual(data["response_count"], 1)
        self.assertEqual(len(data["responses"]), 1)
