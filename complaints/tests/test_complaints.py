from django.test import TestCase
from django.urls import reverse

from accounts.models import Role, User
from agents.models import Agent
from complaints.models import Complaint
from complaints.services import ComplaintError, escalate_complaint, file_complaint, resolve_complaint, start_investigating
from core.models import Area
from members.models import Member


class ComplaintServiceTests(TestCase):
    def setUp(self):
        self.area_a = Area.objects.create(name="AreaA")
        self.area_b = Area.objects.create(name="AreaB")

        mem_user = User.objects.create_user(phone="+256701500000", password="pass12345", role=Role.MEMBER)
        self.member = Member.objects.create(user=mem_user, area=self.area_a)

        agent_user = User.objects.create_user(phone="+256701500001", password="pass12345", role=Role.AGENT)
        self.agent = Agent.objects.create(user=agent_user)
        self.agent.areas.add(self.area_a)

    def test_file_complaint_uses_members_area(self):
        complaint = file_complaint(self.member, "Bad service", "Merchant was rude.")
        self.assertEqual(complaint.area, self.area_a)
        self.assertEqual(complaint.status, Complaint.Status.OPEN)

    def test_empty_subject_rejected(self):
        with self.assertRaises(ComplaintError):
            file_complaint(self.member, "", "Something happened")

    def test_agent_can_start_investigating_in_area(self):
        complaint = file_complaint(self.member, "Bad service", "Details")
        updated = start_investigating(self.agent, complaint.id)
        self.assertEqual(updated.status, Complaint.Status.INVESTIGATING)
        self.assertEqual(updated.assigned_agent, self.agent)

    def test_agent_outside_area_cannot_investigate(self):
        other_member_user = User.objects.create_user(phone="+256701500002", password="pass12345", role=Role.MEMBER)
        other_member = Member.objects.create(user=other_member_user, area=self.area_b)
        complaint = file_complaint(other_member, "Issue", "Details")
        with self.assertRaises(ComplaintError):
            start_investigating(self.agent, complaint.id)

    def test_resolve_complaint(self):
        complaint = file_complaint(self.member, "Bad service", "Details")
        resolved = resolve_complaint(self.agent.user, self.agent, complaint.id, "Refunded the member.")
        self.assertEqual(resolved.status, Complaint.Status.RESOLVED)
        self.assertTrue(hasattr(resolved, "resolution"))

    def test_cannot_resolve_already_closed_complaint(self):
        complaint = file_complaint(self.member, "Bad service", "Details")
        resolve_complaint(self.agent.user, self.agent, complaint.id, "Done.")
        with self.assertRaises(ComplaintError):
            resolve_complaint(self.agent.user, self.agent, complaint.id, "Again?")

    def test_escalate_complaint(self):
        complaint = file_complaint(self.member, "Serious issue", "Details")
        escalated = escalate_complaint(self.agent, complaint.id, "Needs admin attention.")
        self.assertEqual(escalated.status, Complaint.Status.ESCALATED)


class ComplaintAPITests(TestCase):
    def setUp(self):
        self.area = Area.objects.create(name="AreaA")
        mem_user = User.objects.create_user(phone="+256701510000", password="pass12345", role=Role.MEMBER)
        self.member = Member.objects.create(user=mem_user, area=self.area)
        self.member_user = mem_user

        agent_user = User.objects.create_user(phone="+256701510001", password="pass12345", role=Role.AGENT)
        self.agent = Agent.objects.create(user=agent_user)
        self.agent.areas.add(self.area)
        self.agent_user = agent_user

    def test_member_files_and_lists_own_complaints(self):
        self.client.force_login(self.member_user)
        resp = self.client.post(
            reverse("complaints:member_complaints"),
            {"subject": "Late delivery", "description": "Rider never showed up."},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 201)

        resp = self.client.get(reverse("complaints:member_complaints"))
        self.assertEqual(len(resp.json()["data"]), 1)

    def test_agent_sees_only_open_complaints_in_area(self):
        file_complaint(self.member, "Issue", "Details")
        self.client.force_login(self.agent_user)
        resp = self.client.get(reverse("complaints:agent_complaints"))
        self.assertEqual(len(resp.json()["data"]), 1)

    def test_agent_resolves_via_api(self):
        complaint = file_complaint(self.member, "Issue", "Details")
        self.client.force_login(self.agent_user)
        resp = self.client.post(
            reverse("complaints:resolve_complaint", args=[complaint.id]),
            {"resolution_note": "Sorted out."},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["data"]["status"], "resolved")
