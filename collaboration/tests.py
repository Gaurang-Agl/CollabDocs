
# Create your tests here.

from django.db import IntegrityError, transaction
from django.test import TestCase

from rest_framework.test import APIClient

from .models import (
    AuditLog,
    Comment,
    Document,
    DocumentVersion,
    Tag,
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

    # -----------------------------------------------------
    # PERMISSION TESTS
    # -----------------------------------------------------

    def test_viewer_cannot_create_document(self):
        workspace = self.create_workspace()
        WorkspaceMember.objects.create(
            workspace=workspace,
            user=self.user2,
            role=WorkspaceMember.Role.VIEWER,
        )

        viewer_client = APIClient()
        viewer_client.credentials(HTTP_X_USER_ID=str(self.user2.id))

        response = viewer_client.post(
            "/api/documents/",
            {
                "title": "Viewer Doc",
                "content": "Viewer content",
                "workspace": str(workspace.id),
                "status": "draft",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_viewer_cannot_add_member(self):
        workspace = self.create_workspace()
        WorkspaceMember.objects.create(
            workspace=workspace,
            user=self.user2,
            role=WorkspaceMember.Role.VIEWER,
        )

        viewer_client = APIClient()
        viewer_client.credentials(HTTP_X_USER_ID=str(self.user2.id))

        user3 = User.objects.create(
            first_name="Third",
            last_name="User",
            email="third@example.com",
            phone="9000000003",
        )

        response = viewer_client.post(
            f"/api/workspaces/{workspace.id}/members/",
            {
                "user": str(user3.id),
                "role": "viewer",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_editor_cannot_add_member(self):
        workspace = self.create_workspace()
        WorkspaceMember.objects.create(
            workspace=workspace,
            user=self.user2,
            role=WorkspaceMember.Role.EDITOR,
        )

        editor_client = APIClient()
        editor_client.credentials(HTTP_X_USER_ID=str(self.user2.id))

        user3 = User.objects.create(
            first_name="Third",
            last_name="User",
            email="third@example.com",
            phone="9000000003",
        )

        response = editor_client.post(
            f"/api/workspaces/{workspace.id}/members/",
            {
                "user": str(user3.id),
                "role": "viewer",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_non_member_cannot_access_workspace(self):
        workspace = self.create_workspace()
        non_member_client = APIClient()
        non_member_client.credentials(HTTP_X_USER_ID=str(self.user2.id))

        response = non_member_client.get(f"/api/workspaces/{workspace.id}/")
        self.assertEqual(response.status_code, 403)

    def test_missing_x_user_id_returns_403(self):
        workspace = self.create_workspace()
        unauth_client = APIClient()

        response = unauth_client.get(f"/api/workspaces/{workspace.id}/")
        self.assertEqual(response.status_code, 403)
        self.assertIn("X-User-ID", response.data["message"])

    def test_invalid_uuid_x_user_id_returns_403(self):
        workspace = self.create_workspace()
        invalid_client = APIClient()
        invalid_client.credentials(HTTP_X_USER_ID="not-a-valid-uuid")

        response = invalid_client.get(f"/api/workspaces/{workspace.id}/")
        self.assertEqual(response.status_code, 403)

    # -----------------------------------------------------
    # VALIDATION TESTS
    # -----------------------------------------------------

    def test_invalid_email_validation(self):
        response = self.client.post(
            "/api/users/",
            {
                "first_name": "Test",
                "last_name": "Invalid",
                "email": "invalid-email-no-at",
                "phone": "9876543210",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_invalid_phone_validation(self):
        # Non-digits
        response = self.client.post(
            "/api/users/",
            {
                "first_name": "Test",
                "last_name": "Invalid",
                "email": "valid@example.com",
                "phone": "abc1234",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

        # Less than 7 digits
        response = self.client.post(
            "/api/users/",
            {
                "first_name": "Test",
                "last_name": "Invalid",
                "email": "valid@example.com",
                "phone": "12345",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_blank_workspace_name_validation(self):
        response = self.client.post(
            "/api/workspaces/",
            {
                "name": "   ",
                "owner": str(self.user1.id),
                "is_active": True,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_inactive_workspace_cannot_create_document(self):
        workspace = Workspace.objects.create(
            name="Inactive Workspace",
            owner=self.user1,
            is_active=False,
        )
        WorkspaceMember.objects.create(
            workspace=workspace,
            user=self.user1,
            role=WorkspaceMember.Role.ADMIN,
        )

        response = self.client.post(
            "/api/documents/",
            {
                "title": "Inactive Workspace Doc",
                "content": "Content",
                "workspace": str(workspace.id),
                "status": "draft",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_blank_document_title_validation(self):
        workspace = self.create_workspace()
        response = self.client.post(
            "/api/documents/",
            {
                "title": "   ",
                "content": "Valid Content",
                "workspace": str(workspace.id),
                "status": "draft",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_blank_comment_content_validation(self):
        workspace = self.create_workspace()
        document = Document.objects.create(
            title="Comment Test Doc",
            content="Content",
            workspace=workspace,
            created_by=self.user1,
        )
        response = self.client.post(
            "/api/comments/",
            {
                "document": str(document.id),
                "content": "   ",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_tag_validations_and_duplicate_409(self):
        # Blank tag name
        blank_resp = self.client.post(
            "/api/tags/",
            {"name": "   "},
            format="json",
        )
        self.assertEqual(blank_resp.status_code, 400)

        # Exceeds max_length=50
        long_name_resp = self.client.post(
            "/api/tags/",
            {"name": "a" * 51},
            format="json",
        )
        self.assertEqual(long_name_resp.status_code, 400)

        # Valid create
        create_resp = self.client.post(
            "/api/tags/",
            {"name": "unique-tag-test"},
            format="json",
        )
        self.assertEqual(create_resp.status_code, 201)

        # Duplicate returns 409
        dup_resp = self.client.post(
            "/api/tags/",
            {"name": "unique-tag-test"},
            format="json",
        )
        self.assertEqual(dup_resp.status_code, 409)

    def test_document_tags_attachment_and_duplicate_prevention(self):
        workspace = self.create_workspace()
        document = Document.objects.create(
            title="Tagged Doc",
            content="Tagged Content",
            workspace=workspace,
            created_by=self.user1,
        )
        tag1 = Tag.objects.create(name="tag-alpha")
        tag2 = Tag.objects.create(name="tag-beta")

        # Duplicate tag IDs in payload returns 400
        dup_payload_resp = self.client.post(
            f"/api/documents/{document.id}/tags/",
            {"tag_ids": [str(tag1.id), str(tag1.id)]},
            format="json",
        )
        self.assertEqual(dup_payload_resp.status_code, 400)

        # Attach valid tags
        attach_resp = self.client.post(
            f"/api/documents/{document.id}/tags/",
            {"tag_ids": [str(tag1.id), str(tag2.id)]},
            format="json",
        )
        self.assertEqual(attach_resp.status_code, 200)
        self.assertEqual(document.tags.count(), 2)

    # -----------------------------------------------------
    # FILTERING & SEARCH TESTS
    # -----------------------------------------------------

    def test_document_search_via_q_object(self):
        workspace = self.create_workspace()
        doc1 = Document.objects.create(
            title="Python Architecture Guide",
            content="General details",
            workspace=workspace,
            created_by=self.user1,
            status=Document.Status.PUBLISHED,
        )
        doc2 = Document.objects.create(
            title="Database Schema",
            content="Contains python references in the body",
            workspace=workspace,
            created_by=self.user1,
            status=Document.Status.PUBLISHED,
        )
        doc3 = Document.objects.create(
            title="Frontend Guide",
            content="React components only",
            workspace=workspace,
            created_by=self.user1,
            status=Document.Status.PUBLISHED,
        )

        response = self.client.get("/api/documents/?search=Python")
        self.assertEqual(response.status_code, 200)
        result_ids = [d["id"] for d in response.data]
        self.assertIn(str(doc1.id), result_ids)
        self.assertIn(str(doc2.id), result_ids)
        self.assertNotIn(str(doc3.id), result_ids)

    def test_document_status_filter(self):
        workspace = self.create_workspace()
        doc_draft = Document.objects.create(
            title="Draft Doc",
            content="Draft",
            workspace=workspace,
            created_by=self.user1,
            status=Document.Status.DRAFT,
        )
        doc_pub = Document.objects.create(
            title="Published Doc",
            content="Published",
            workspace=workspace,
            created_by=self.user1,
            status=Document.Status.PUBLISHED,
        )

        response = self.client.get("/api/documents/?status=published")
        self.assertEqual(response.status_code, 200)
        result_ids = [d["id"] for d in response.data]
        self.assertIn(str(doc_pub.id), result_ids)
        self.assertNotIn(str(doc_draft.id), result_ids)

    # -----------------------------------------------------
    # AGGREGATION & AUDIT TESTS
    # -----------------------------------------------------

    def test_workspace_summary_aggregation(self):
        workspace = self.create_workspace()
        Document.objects.create(
            title="Doc 1",
            content="Content 1",
            workspace=workspace,
            created_by=self.user1,
            status=Document.Status.PUBLISHED,
        )
        Document.objects.create(
            title="Doc 2",
            content="Content 2",
            workspace=workspace,
            created_by=self.user1,
            status=Document.Status.DRAFT,
        )

        response = self.client.get(f"/api/workspaces/{workspace.id}/summary/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["total_members"], 1)
        self.assertEqual(response.data["total_documents"], 2)
        self.assertIn("documents_by_status", response.data)

    def test_document_stats_aggregation(self):
        workspace = self.create_workspace()
        create_resp = self.client.post(
            "/api/documents/",
            {
                "title": "Stats Doc",
                "content": "Initial",
                "workspace": str(workspace.id),
                "status": "draft",
            },
            format="json",
        )
        doc_id = create_resp.data["id"]

        # Update to create second version
        self.client.put(
            f"/api/documents/{doc_id}/",
            {
                "title": "Stats Doc Updated",
                "content": "Second",
                "workspace": str(workspace.id),
                "status": "published",
            },
            format="json",
        )

        # Add comment
        self.client.post(
            "/api/comments/",
            {
                "document": str(doc_id),
                "content": "Great documentation!",
            },
            format="json",
        )

        response = self.client.get(f"/api/documents/{doc_id}/stats/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["version_count"], 2)
        self.assertEqual(response.data["comment_count"], 1)
        self.assertEqual(response.data["contributor_count"], 1)

    def test_audit_logs_endpoint_and_filtering(self):
        workspace = self.create_workspace()
        self.client.post(
            "/api/documents/",
            {
                "title": "Audit Filter Doc",
                "content": "Filter content",
                "workspace": str(workspace.id),
                "status": "draft",
            },
            format="json",
        )

        response = self.client.get("/api/audit-logs/?model_name=Document&actions=created")
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["model_name"], "Document")
        self.assertEqual(response.data[0]["action"], "created")

    def test_duplicate_user_case_insensitive_returns_409(self):
        # First creation
        resp1 = self.client.post(
            "/api/users/",
            {
                "first_name": "Unique",
                "last_name": "One",
                "email": "unique_case@example.com",
                "phone": "9111111111",
            },
            format="json",
        )
        self.assertEqual(resp1.status_code, 201)

        # Duplicate email with different casing
        resp2 = self.client.post(
            "/api/users/",
            {
                "first_name": "Unique",
                "last_name": "Two",
                "email": "UNIQUE_CASE@EXAMPLE.COM",
                "phone": "9222222222",
            },
            format="json",
        )
        self.assertEqual(resp2.status_code, 409)

    def test_document_serializer_exposes_tags_after_attach(self):
        workspace = self.create_workspace()
        doc = Document.objects.create(
            title="Tagged Display Doc",
            content="Content",
            workspace=workspace,
            created_by=self.user1,
        )
        tag1 = Tag.objects.create(name="python-dev")
        tag2 = Tag.objects.create(name="backend-dev")

        self.client.post(
            f"/api/documents/{doc.id}/tags/",
            {"tag_ids": [str(tag1.id), str(tag2.id)]},
            format="json",
        )

        # GET /documents/ should now show tags list
        list_resp = self.client.get("/api/documents/")
        self.assertEqual(list_resp.status_code, 200)
        doc_data = next((d for d in list_resp.data if d["id"] == str(doc.id)), None)
        self.assertIsNotNone(doc_data)
        self.assertIn("tags", doc_data)
        self.assertEqual(set(doc_data["tags"]), {"python-dev", "backend-dev"})

    def test_cannot_move_document_to_different_workspace_on_update(self):
        workspace1 = self.create_workspace()
        workspace2 = Workspace.objects.create(
            name="Second Workspace",
            owner=self.user1,
            is_active=True,
        )
        WorkspaceMember.objects.create(
            workspace=workspace2,
            user=self.user1,
            role=WorkspaceMember.Role.ADMIN,
        )

        doc = Document.objects.create(
            title="Original Workspace Doc",
            content="Content",
            workspace=workspace1,
            created_by=self.user1,
        )

        # Attempt to PUT document with different workspace
        put_resp = self.client.put(
            f"/api/documents/{doc.id}/",
            {
                "title": "Hacked Workspace Doc",
                "content": "Content",
                "workspace": str(workspace2.id),
                "status": "draft",
            },
            format="json",
        )
        self.assertEqual(put_resp.status_code, 400)
        self.assertIn("workspace", str(put_resp.data))

    def test_workspace_and_member_audit_logging(self):
        workspace = self.create_workspace()
        # Verify workspace creation was audit logged
        self.assertTrue(
            AuditLog.objects.filter(
                model_name="Workspace",
                object_id=str(workspace.id),
                action="created",
            ).exists()
        )

        # Add a member
        member_resp = self.client.post(
            f"/api/workspaces/{workspace.id}/members/",
            {
                "user": str(self.user2.id),
                "role": "editor",
            },
            format="json",
        )
        self.assertEqual(member_resp.status_code, 201)
        member_id = member_resp.data["id"]

        # Verify member creation was audit logged
        self.assertTrue(
            AuditLog.objects.filter(
                model_name="WorkspaceMember",
                object_id=str(member_id),
                action="created",
            ).exists()
        )

    def test_list_users(self):
        response = self.client.get("/api/users/")
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(len(response.data), 2)
        user_ids = [u["id"] for u in response.data]
        self.assertIn(str(self.user1.id), user_ids)
        self.assertIn(str(self.user2.id), user_ids)

    def test_list_users_filtering(self):
        # Email filter
        response = self.client.get(
            f"/api/users/?email={self.user1.email}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["id"], str(self.user1.id))

        # Search filter
        response = self.client.get("/api/users/?search=Rahul")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["id"], str(self.user2.id))

    def test_list_workspaces(self):
        workspace = self.create_workspace()
        # With X-User-ID header (set in setUp to user1)
        response = self.client.get("/api/workspaces/")
        self.assertEqual(response.status_code, 200)
        workspace_ids = [w["id"] for w in response.data]
        self.assertIn(str(workspace.id), workspace_ids)

    def test_list_workspaces_member_filter(self):
        workspace = self.create_workspace()
        # user2 is not a member of workspace yet
        client2 = APIClient()
        client2.credentials(HTTP_X_USER_ID=str(self.user2.id))
        response = client2.get("/api/workspaces/")
        self.assertEqual(response.status_code, 200)
        workspace_ids = [w["id"] for w in response.data]
        self.assertNotIn(str(workspace.id), workspace_ids)

        # Without X-User-ID header returns all workspaces
        anon_client = APIClient()
        response = anon_client.get("/api/workspaces/")
        self.assertEqual(response.status_code, 200)
        workspace_ids = [w["id"] for w in response.data]
        self.assertIn(str(workspace.id), workspace_ids)

    def test_retrieve_document(self):
        workspace = self.create_workspace()
        doc_resp = self.client.post(
            "/api/documents/",
            {
                "title": "Doc for Retrieval",
                "content": "Content here",
                "workspace": str(workspace.id),
                "status": "draft",
            },
            format="json",
        )
        self.assertEqual(doc_resp.status_code, 201)
        doc_id = doc_resp.data["id"]

        # Retrieve document
        response = self.client.get(f"/api/documents/{doc_id}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["id"], doc_id)
        self.assertEqual(response.data["title"], "Doc for Retrieval")

    def test_retrieve_comment(self):
        workspace = self.create_workspace()
        doc_resp = self.client.post(
            "/api/documents/",
            {
                "title": "Doc for Comment",
                "content": "Content",
                "workspace": str(workspace.id),
                "status": "draft",
            },
            format="json",
        )
        doc_id = doc_resp.data["id"]

        comment_resp = self.client.post(
            "/api/comments/",
            {
                "document": doc_id,
                "content": "Nice document!",
            },
            format="json",
        )
        self.assertEqual(comment_resp.status_code, 201)
        comment_id = comment_resp.data["id"]

        response = self.client.get(f"/api/comments/{comment_id}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["id"], comment_id)
        self.assertEqual(response.data["content"], "Nice document!")

    def test_list_and_retrieve_tags(self):
        tag_resp = self.client.post(
            "/api/tags/",
            {"name": "backend-test"},
            format="json",
        )
        self.assertEqual(tag_resp.status_code, 201)
        tag_id = tag_resp.data["id"]

        # List tags
        list_resp = self.client.get("/api/tags/")
        self.assertEqual(list_resp.status_code, 200)
        tag_ids = [t["id"] for t in list_resp.data]
        self.assertIn(tag_id, tag_ids)

        # Retrieve tag
        get_resp = self.client.get(f"/api/tags/{tag_id}/")
        self.assertEqual(get_resp.status_code, 200)
        self.assertEqual(get_resp.data["name"], "backend-test")

    def test_retrieve_audit_log(self):
        workspace = self.create_workspace()
        log = AuditLog.objects.filter(
            model_name="Workspace",
            object_id=str(workspace.id),
        ).first()
        self.assertIsNotNone(log)

        response = self.client.get(f"/api/audit-logs/{log.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["id"], str(log.id))

    def test_update_member_role(self):
        workspace = self.create_workspace()
        # Add user2 as editor
        self.client.post(
            f"/api/workspaces/{workspace.id}/members/",
            {"user": str(self.user2.id), "role": "editor"},
            format="json",
        )

        # Update user2 to viewer
        update_resp = self.client.patch(
            f"/api/workspaces/{workspace.id}/members/",
            {"user": str(self.user2.id), "role": "viewer"},
            format="json",
        )
        self.assertEqual(update_resp.status_code, 200)
        self.assertEqual(update_resp.data["role"], "viewer")

        # Verify viewer cannot create document
        client2 = APIClient()
        client2.credentials(HTTP_X_USER_ID=str(self.user2.id))
        doc_resp = client2.post(
            "/api/documents/",
            {
                "title": "Unauthorized Doc",
                "content": "Fail",
                "workspace": str(workspace.id),
                "status": "draft",
            },
            format="json",
        )
        self.assertEqual(doc_resp.status_code, 403)
        self.assertEqual(
            doc_resp.data["message"],
            "User does not have the required workspace role.",
        )

    def test_phone_max_length_validation(self):
        response = self.client.post(
            "/api/users/",
            {
                "first_name": "Test",
                "last_name": "LongPhone",
                "email": "longphone@example.com",
                "phone": "1234567890123456",  # 16 digits > 15
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("phone", response.data["errors"])

    def test_user_update_and_delete_not_allowed(self):
        # PUT /api/users/{id}/ should return 405
        put_resp = self.client.put(
            f"/api/users/{self.user1.id}/",
            {"first_name": "Hacked"},
            format="json",
        )
        self.assertEqual(put_resp.status_code, 405)

        # DELETE /api/users/{id}/ should return 405
        del_resp = self.client.delete(f"/api/users/{self.user1.id}/")
        self.assertEqual(del_resp.status_code, 405)

    def test_workspace_update_requires_admin(self):
        workspace = self.create_workspace()

        # Non-admin / unauthenticated cannot update workspace
        unauth_client = APIClient()
        unauth_resp = unauth_client.put(
            f"/api/workspaces/{workspace.id}/",
            {"name": "Renamed Workspace", "owner": str(self.user1.id)},
            format="json",
        )
        self.assertEqual(unauth_resp.status_code, 403)

        # Admin (owner) can update workspace
        admin_resp = self.client.put(
            f"/api/workspaces/{workspace.id}/",
            {"name": "Renamed Workspace", "owner": str(self.user1.id)},
            format="json",
        )
        self.assertEqual(admin_resp.status_code, 200)
        self.assertEqual(admin_resp.data["name"], "Renamed Workspace")

    def test_workspace_owner_cannot_be_demoted(self):
        workspace = self.create_workspace()

        # Try to demote owner (user1) to viewer
        demote_resp = self.client.patch(
            f"/api/workspaces/{workspace.id}/members/",
            {"user": str(self.user1.id), "role": "viewer"},
            format="json",
        )
        self.assertEqual(demote_resp.status_code, 400)
        self.assertEqual(
            demote_resp.data["message"],
            "Workspace owner role cannot be demoted.",
        )