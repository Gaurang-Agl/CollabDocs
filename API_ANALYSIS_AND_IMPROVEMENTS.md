# CollabDocs API Architecture & Security Audit Report

## 1. Executive Summary

This report delivers an in-depth, end-to-end evaluation of the CollabDocs REST API backend. It examines all data models, ViewSets, serializers, permissions, custom middleware, database transactions, signals, and test coverage across the system. 

The evaluation identifies specific functional gaps, authorization loopholes, concurrency edge cases, and architectural improvement points across all 17+ API endpoints.

---

## 2. API Endpoint Behavioral & Vulnerability Audit

### 2.1 Users (/api/users/)

#### Current Behavior
- POST /api/users/: Validates email (@ check, stripped, lowercased) and phone (numeric check, length >= 7). Unique constraint violations raise IntegrityError inside an atomic transaction and return 409 Conflict.
- GET /api/users/: Returns list of all users ordered by creation date. Supports ?email= and ?search= query parameters.
- GET /api/users/{id}/: Retrieves individual user details.

#### Identified Loopholes & Areas for Improvement
1. **Unprotected PUT/PATCH/DELETE on User Endpoints:**
   - UserViewSet inherits ModelViewSet without restricting http_method_names.
   - As a result, PUT /api/users/{id}/, PATCH /api/users/{id}/, and DELETE /api/users/{id}/ are accidentally exposed.
   - Any client can modify or delete user records without authentication (X-User-ID is not checked).
   - Calling DELETE /api/users/{id}/ cascades and permanently deletes all workspaces, documents, and comments owned by that user.
   - Calling PUT/PATCH to set an email or phone to an existing record does not catch IntegrityError, causing an unhandled 500 Internal Server Error instead of 409 Conflict.
   - **Fix:** Restrict http_method_names = ['get', 'post'] on UserViewSet.

2. **Phone Number Length Boundary Overflow:**
   - In models.User, phone = models.CharField(max_length=15, unique=True).
   - In UserSerializer.validate_phone, the serializer checks len(value) < 7, but does not enforce len(value) <= 15 because default validators were bypassed with extra_kwargs = {'phone': {'validators': []}}.
   - Submitting a 16+ digit phone number bypasses serializer validation and triggers a database DataError: value too long for type character varying(15), producing an unhandled 500 Internal Server Error.
   - **Fix:** Add if len(value) > 15: raise serializers.ValidationError('Phone number cannot exceed 15 digits.') in validate_phone.

3. **Loose Email Format Validation:**
   - validate_email only checks if '@' not in value. Strings such as 'user@', '@domain', or 'a@b' are accepted.
   - **Fix:** Use Django standard django.core.validators.validate_email for RFC-compliant format checks.

4. **Whitespace-Only Name Strings:**
   - first_name and last_name can be submitted as blank spaces ('   ').
   - **Fix:** Add validators ensuring first_name.strip() and last_name.strip() are not empty.

---

### 2.2 Workspaces (/api/workspaces/)

#### Current Behavior
- POST /api/workspaces/: Enforces X-User-ID == owner.id. Creates workspace, adds owner as admin member, and logs an AuditLog in a single atomic transaction.
- GET /api/workspaces/: Filters workspaces where the actor is a member if X-User-ID is provided. If X-User-ID is omitted, returns all workspaces.
- GET /api/workspaces/{id}/: Requires membership (admin, editor, or viewer).
- GET /api/workspaces/{id}/summary/: Aggregates member count, document count, and document status distribution.

#### Identified Loopholes & Areas for Improvement
1. **Critical Authorization Bypass on Workspace Update (PUT/PATCH):**
   - In views.py, WorkspaceViewSet.http_method_names was expanded to ['get', 'post', 'put', 'patch'] to support the custom member update action.
   - However, WorkspaceViewSet did not define custom update() or partial_update() methods.
   - Therefore, DRF exposes the default ModelViewSet.update() at PUT /api/workspaces/{id}/ and PATCH /api/workspaces/{id}/.
   - Any external client can rename, deactivate, or modify any workspace without an X-User-ID header or membership check.
   - Furthermore, owner is not marked read-only in WorkspaceSerializer, allowing arbitrary reassignment of workspace ownership.
   - **Fix:** Implement explicit update() and partial_update() methods requiring WorkspaceMember.Role.ADMIN, mark owner immutable on updates, and generate an audit log on modification.

2. **Workspace Deletion Not Supported:**
   - No soft-delete or hard-delete capability exists for workspaces if an owner wishes to archive or remove a workspace.
   - **Fix:** Provide a soft-deactivation endpoint or explicit DELETE action restricted strictly to the workspace owner.

3. **Status Distribution Aggregation Completeness:**
   - In GET /api/workspaces/{id}/summary/, documents_by_status groups only existing statuses. If a workspace has 0 archived documents, 'archived' is absent from the response.
   - **Fix:** Return standard keys (draft, published, archived) with default count 0 for consistent client rendering.

---

### 2.3 Workspace Members (/api/workspaces/{id}/members/)

#### Current Behavior
- GET /api/workspaces/{id}/members/: Requires workspace membership. Supports filtering by roles, joined_after, joined_before, and email.
- POST /api/workspaces/{id}/members/: Requires admin role. Returns 409 Conflict if membership already exists.
- PUT / PATCH /api/workspaces/{id}/members/: Requires admin role. Updates member role.

#### Identified Loopholes & Areas for Improvement
1. **Workspace Owner Demotion Loophole:**
   - An administrator can send a PATCH request setting the workspace owner role to viewer or editor.
   - **Fix:** Prevent demoting the workspace owner (if member.user_id == workspace.owner_id: raise PermissionDenied('Workspace owner role cannot be modified.')).

2. **Last Administrator Lockout Loophole:**
   - The only administrator in a workspace can demote themselves to viewer, permanently stranding the workspace with no administrator to manage members.
   - **Fix:** Validate that at least one admin remains before allowing an admin demotion.

3. **Member Removal Endpoint Missing:**
   - There is no endpoint to remove a member from a workspace (DELETE /api/workspaces/{id}/members/).
   - Once added, a member can never be revoked.
   - **Fix:** Add a delete method to the members action requiring admin permissions, preventing removal of the workspace owner.

4. **Invalid Date Filter Exception Handling:**
   - In GET /api/workspaces/{id}/members/, passing invalid query param strings like ?joined_after=invalid-date results in database-level errors on PostgreSQL.
   - **Fix:** Validate date strings before filtering.

---

### 2.4 Documents (/api/documents/)

#### Current Behavior
- POST /api/documents/: Requires admin or editor role in the target workspace. Verifies workspace is active. Automatically creates version 1 and triggers an audit log.
- GET /api/documents/: Scoped to workspaces where actor is a member. Supports status, statuses, workspace, tags, date filters, and Q-based search on title/content.
- GET /api/documents/{id}/: Scoped to workspace members.
- PUT /api/documents/{id}/: Requires admin or editor role. Prohibits changing workspace or saving to inactive workspaces. Increments version number and triggers audit log.
- GET /api/documents/{id}/versions/: Returns document version history.
- GET /api/documents/{id}/stats/: Returns version count, comment count, and unique contributor count.
- POST /api/documents/{id}/tags/: Validates duplicate and non-existent tag IDs. Attaches tags atomically.

#### Identified Loopholes & Areas for Improvement
1. **Missing PATCH Support for Document Updates:**
   - DocumentViewSet.http_method_names currently allows only ['get', 'post', 'put'].
   - A client attempting to send PATCH /api/documents/{id}/ receives 405 Method Not Allowed.
   - Standard REST conventions expect PATCH support for partial document updates (e.g. updating title only, or updating status only).
   - **Fix:** Add 'patch' to http_method_names and support partial updates.

2. **Concurrency / Race Condition in Version Numbering:**
   - In both create() and update(), the new version number is computed via document.versions.count() + 1.
   - Under concurrent updates from multiple editors, two simultaneous requests can read the same count and assign duplicate version numbers.
   - Furthermore, DocumentVersion lacks a database uniqueness constraint on ['document', 'version_number'].
   - **Fix:** Use select_for_update() inside the atomic transaction and add a UniqueConstraint(fields=['document', 'version_number'], name='unique_document_version') on DocumentVersion.

3. **Contributor Count Skew When User is Deleted:**
   - In DocumentViewSet.stats:
     contributor_ids = document.versions.values_list('saved_by_id', flat=True).distinct()
   - If a user who saved an earlier version is deleted, saved_by_id becomes None (due to SET_NULL).
   - The query counts None as a unique contributor.
   - **Fix:** Filter out nulls: document.versions.exclude(saved_by__isnull=True).values_list('saved_by_id', flat=True).distinct().count().

4. **Tagging Actions Omit Audit Logging & Timestamp Refresh:**
   - Calling POST /api/documents/{id}/tags/ modifies the many-to-many through table but does not create an AuditLog entry.
   - It also does not refresh document.updated_at.
   - **Fix:** Create an AuditLog record (action='tagged') and touch document.save(update_fields=['updated_at']).

5. **Tag Removal Endpoint Missing:**
   - No endpoint exists to detach or remove tags from a document.
   - **Fix:** Add a DELETE /api/documents/{id}/tags/ action.

---

### 2.5 Comments (/api/comments/)

#### Current Behavior
- POST /api/comments/: Requires workspace membership (admin, editor, or viewer). Automatically sets author=actor. Validates that reply comments belong to the same document as the parent.
- GET /api/comments/?document={id}: Requires document query parameter. Scoped to workspace members. Returns top-level comments with nested replies.
- GET /api/comments/{id}/: Scoped to workspace members.

#### Identified Loopholes & Areas for Improvement
1. **Comments Allowed on Inactive Workspaces & Archived Documents:**
   - CommentViewSet.create verifies membership but does not check whether document.workspace.is_active is True.
   - Members can post comments into deactivated workspaces and archived documents.
   - **Fix:** Check if not document.workspace.is_active: raise ValidationError('Cannot post comments in an inactive workspace.') and optionally verify document status is not archived.

2. **Single-Level Reply Nesting Limitation:**
   - In CommentSerializer.get_replies:
     if obj.parent is None: children = obj.replies.all()
   - If a reply is added to another reply (nested depth >= 2), the nested reply is omitted from the response hierarchy because parent is not null.
   - **Fix:** Enforce that replies can only target top-level comments (if parent.parent is not None: raise ValidationError('Nested replies beyond level 1 are not allowed.')), ensuring data structure consistency.

3. **Comment Editing & Deletion Missing:**
   - No endpoints exist for authors to edit or delete their comments.
   - **Fix:** Add PUT/PATCH and DELETE on /api/comments/{id}/ permitting author or workspace admin.

---

### 2.6 Tags (/api/tags/)

#### Current Behavior
- POST /api/tags/: Creates tag with normalized lowercase name. Duplicate names return 409 Conflict.
- GET /api/tags/: Lists all tags.
- GET /api/tags/{id}/: Retrieves tag details.

#### Identified Loopholes & Areas for Improvement
1. **Unrestricted Public Creation of Tags:**
   - Any unauthenticated user can call POST /api/tags/ without X-User-ID.
   - Malicious clients could flood the tag database.
   - **Fix:** Require X-User-ID header on tag creation, or require workspace-scoped tag management.

---

### 2.7 Audit Logs (/api/audit-logs/)

#### Current Behavior
- GET /api/audit-logs/: Accessible only if actor is an admin in any workspace. Supports filtering by actions, model_name, timestamp_after, timestamp_before.
- GET /api/audit-logs/{id}/: Accessible only to administrators.

#### Identified Loopholes & Areas for Improvement
1. **Critical Cross-Tenant Information Disclosure:**
   - The permission check verifies:
     WorkspaceMember.objects.filter(user=actor, role=ADMIN).exists()
   - If User A is an admin in Workspace 1, they can see all audit logs in the system, including documents, workspaces, and actions from Workspace 2, 3, etc.
   - **Fix:** Restrict audit log retrieval to entities associated with workspaces where the actor is an administrator, or provide a ?workspace= query parameter that verifies admin privileges for that specific workspace.

2. **Missing Pagination on Audit Log List:**
   - In production systems, audit logs grow rapidly. Returning all logs unpaginated risks high memory usage.
   - **Fix:** Implement standard cursor or limit/offset pagination on AuditLogViewSet.

---

## 3. Prioritized Fix Plan

| Priority | Component | Issue | Proposed Remediation |
|---|---|---|---|
| **High** | WorkspaceViewSet | PUT/PATCH /api/workspaces/{id}/ exposed without authorization | Override update/partial_update, enforce ADMIN role, make owner read-only, log AuditLog |
| **High** | UserViewSet | PUT/PATCH/DELETE exposed with no auth and uncaught IntegrityError | Set http_method_names = ['get', 'post'] on UserViewSet |
| **High** | WorkspaceViewSet.members | Workspace owner can be demoted / Last admin can demote self | Add guard preventing owner demotion and ensuring at least one admin exists |
| **Medium** | UserSerializer | Phone number length > 15 causes 500 error on PostgreSQL | Add max length validation (<= 15 digits) in validate_phone |
| **Medium** | CommentViewSet | Comments allowed on deactivated workspaces | Check document.workspace.is_active before creating comment |
| **Medium** | DocumentViewSet | version_number concurrency race condition | Add select_for_update() on document and add DB unique constraint |
| **Medium** | AuditLogViewSet | Multi-tenant audit log leak | Filter audit logs to workspaces where actor is admin |
| **Low** | DocumentViewSet | stats counts None as contributor if user is deleted | Exclude saved_by__isnull=True in distinct contributor count |
| **Low** | DocumentViewSet | Adding tags does not log audit or update updated_at | Add AuditLog entry on tag attachment and touch timestamp |

---

## 4. Verification & Testing Strategy

1. **Automated Unit Tests:** Add dedicated test cases in collaboration/tests.py verifying each fix:
   - Verify non-admin cannot update workspace (PUT/PATCH /api/workspaces/{id}/ returns 403).
   - Verify workspace owner cannot be demoted (returns 403/400).
   - Verify phone > 15 digits returns 400 validation error instead of 500.
   - Verify comments cannot be posted to inactive workspaces.
   - Verify document version uniqueness.
2. **Regression Check:** Run python manage.py test to ensure all 40+ existing tests continue passing without regression.
3. **Local Staging Verification:** Execute Postman collection tests against a running test server.

---

## 5. Implementation Status of High-Risk Boundary Fixes (Category B)

The following defensive fixes have been implemented and verified locally without breaking any existing behavior:

1. **UserViewSet Method Restriction:**
   - Added http_method_names = ['get', 'post'] to UserViewSet in collaboration/views.py.
   - Prevents unauthenticated PUT, PATCH, and DELETE requests on /api/users/{id}/.

2. **Phone Number Length Boundary Validation:**
   - Added len(value) <= 15 validation to UserSerializer.validate_phone in collaboration/serializers.py.
   - Prevents database DataError and unhandled 500 server errors when phone exceeds 15 digits.

3. **Workspace Update Permissions & Audit Logging:**
   - Implemented explicit update() and partial_update() on WorkspaceViewSet requiring WorkspaceMember.Role.ADMIN.
   - Prohibits unauthorized workspace updates and prevents transferring workspace ownership.
   - Automatically writes an AuditLog entry with ction='updated' and model_name='Workspace'.

4. **Workspace Owner Demotion Protection:**
   - Added validation in WorkspaceViewSet.members preventing demoting the workspace owner's role from ADMIN.

5. **Automated Verification:**
   - Added 4 dedicated unit tests in collaboration/tests.py covering all boundary conditions.
   - Total test suite: **44 tests passing** (0 failures, 0 errors).
