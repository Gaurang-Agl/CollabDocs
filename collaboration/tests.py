
# Create your tests here.

from django.db import IntegrityError, transaction
from django.test import TestCase

from rest_framework.test import APIClient

from .models import (
    AuditLog,
    Comment,
    Document,
    DocumentVersion,
    User,
    Workspace,
    WorkspaceMember,
)


class CollabDocsAPITests(TestCase):

    def setUp(self):
        self.client = APIClient()

        self.user1 = User.objects.create(
            first_name="Gaurang",
            last_name="Agarwal",
            email="gaurang_test@example.com",
            phone="9000000001",
        )

        self.user2 = User.objects.create(
            first_name="Rahul",
            last_name="Tester",
            email="rahul_test@example.com",
            phone="9000000002",
        )

        self.client.credentials(
            HTTP_X_USER_ID=str(self.user1.id)
        )

    def create_workspace(self):
        response = self.client.post(
            "/api/workspaces/",
            {
                "name": "Test Workspace",
                "owner": str(self.user1.id),
                "is_active": True,
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            201,
        )

        return Workspace.objects.get(
            id=response.data["id"]
        )

    def test_workspace_owner_becomes_admin(self):
        workspace = self.create_workspace()

        self.assertTrue(
            WorkspaceMember.objects.filter(
                workspace=workspace,
                user=self.user1,
                role=WorkspaceMember.Role.ADMIN,
            ).exists()
        )

    def test_duplicate_member_returns_409(self):
        workspace = self.create_workspace()

        response = self.client.post(
            f"/api/workspaces/{workspace.id}/members/",
            {
                "user": str(self.user1.id),
                "role": "viewer",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            409,
        )

    def test_transaction_rolls_back(self):
        workspace_id = None

        try:
            with transaction.atomic():

                workspace = Workspace.objects.create(
                    name="Rollback Workspace",
                    owner=self.user1,
                )

                workspace_id = workspace.id

                WorkspaceMember.objects.create(
                    workspace=workspace,
                    user=self.user1,
                    role=WorkspaceMember.Role.ADMIN,
                )

                # Intentional duplicate.
                WorkspaceMember.objects.create(
                    workspace=workspace,
                    user=self.user1,
                    role=WorkspaceMember.Role.ADMIN,
                )

        except IntegrityError:
            pass

        self.assertIsNotNone(
            workspace_id
        )

        self.assertFalse(
            Workspace.objects.filter(
                id=workspace_id
            ).exists()
        )

        self.assertFalse(
            WorkspaceMember.objects.filter(
                workspace_id=workspace_id
            ).exists()
        )

    def test_document_create_creates_version(self):
        workspace = self.create_workspace()

        response = self.client.post(
            "/api/documents/",
            {
                "title": "Test Document",
                "content": "Version one",
                "workspace": str(workspace.id),
                "status": "draft",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            201,
        )

        document = Document.objects.get(
            id=response.data["id"]
        )

        self.assertEqual(
            document.versions.count(),
            1,
        )

        version = document.versions.first()

        self.assertEqual(
            version.version_number,
            1,
        )

    def test_document_update_creates_second_version(self):
        workspace = self.create_workspace()

        create_response = self.client.post(
            "/api/documents/",
            {
                "title": "Version Test",
                "content": "First version",
                "workspace": str(workspace.id),
                "status": "draft",
            },
            format="json",
        )

        self.assertEqual(
            create_response.status_code,
            201,
        )

        document_id = create_response.data["id"]

        update_response = self.client.put(
            f"/api/documents/{document_id}/",
            {
                "title": "Version Test Updated",
                "content": "Second version",
                "workspace": str(workspace.id),
                "status": "published",
            },
            format="json",
        )

        self.assertEqual(
            update_response.status_code,
            200,
        )

        document = Document.objects.get(
            id=document_id
        )

        self.assertEqual(
            document.versions.count(),
            2,
        )

        version_numbers = list(
            document.versions
            .order_by("version_number")
            .values_list(
                "version_number",
                flat=True,
            )
        )

        self.assertEqual(
            version_numbers,
            [1, 2],
        )

    def test_document_create_generates_audit_log(self):
        workspace = self.create_workspace()

        response = self.client.post(
            "/api/documents/",
            {
                "title": "Audit Test",
                "content": "Audit content",
                "workspace": str(workspace.id),
                "status": "draft",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            201,
        )

        document_id = response.data["id"]

        self.assertTrue(
            AuditLog.objects.filter(
                object_id=str(document_id),
                model_name="Document",
                action="created",
            ).exists()
        )

    def test_document_update_generates_updated_audit_log(self):
        workspace = self.create_workspace()

        create_response = self.client.post(
            "/api/documents/",
            {
                "title": "Audit Update Test",
                "content": "Original",
                "workspace": str(workspace.id),
                "status": "draft",
            },
            format="json",
        )

        document_id = create_response.data["id"]

        response = self.client.put(
            f"/api/documents/{document_id}/",
            {
                "title": "Audit Update Test Changed",
                "content": "Updated",
                "workspace": str(workspace.id),
                "status": "published",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertTrue(
            AuditLog.objects.filter(
                object_id=str(document_id),
                model_name="Document",
                action="updated",
            ).exists()
        )

    def test_comment_reply_must_use_same_document(self):
        workspace = self.create_workspace()

        document1 = Document.objects.create(
            title="Document One",
            content="One",
            workspace=workspace,
            created_by=self.user1,
        )

        document2 = Document.objects.create(
            title="Document Two",
            content="Two",
            workspace=workspace,
            created_by=self.user1,
        )

        parent = Comment.objects.create(
            document=document1,
            author=self.user1,
            content="Parent comment",
        )

        response = self.client.post(
            "/api/comments/",
            {
                "document": str(document2.id),
                "content": "Invalid reply",
                "parent": str(parent.id),
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            400,
        )