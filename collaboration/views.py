from django.db import IntegrityError, transaction
from django.db.models import Count, Q

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import (
    NotAuthenticated,
    NotFound,
    PermissionDenied,
)
from rest_framework.response import Response

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

from .permissions import (
    get_actor,
    require_workspace_role,
)

from .serializers import (
    AuditLogSerializer,
    CommentSerializer,
    DocumentSerializer,
    DocumentTagSerializer,
    DocumentVersionSerializer,
    TagSerializer,
    UserSerializer,
    WorkspaceMemberSerializer,
    WorkspaceSerializer,
)


# =========================================================
# USERS
# =========================================================

class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all().order_by("-created_at")
    serializer_class = UserSerializer

    # Assignment only requires:
    # POST /api/users/
    # GET  /api/users/{id}/
    http_method_names = ["get", "post"]

    def list(self, request, *args, **kwargs):
        return Response(
            {
                "message": (
                    "User list endpoint is not part "
                    "of the required API."
                )
            },
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )


# =========================================================
# WORKSPACES
# =========================================================

class WorkspaceViewSet(viewsets.ModelViewSet):
    serializer_class = WorkspaceSerializer

    # Required:
    # POST /api/workspaces/
    # GET  /api/workspaces/{id}/
    # custom members + summary
    http_method_names = ["get", "post"]

    def get_queryset(self):
        return (
            Workspace.objects
            .select_related("owner")
            .annotate(
                member_count=Count(
                    "members",
                    distinct=True,
                ),
                document_count=Count(
                    "documents",
                    distinct=True,
                ),
            )
        )

    def list(self, request, *args, **kwargs):
        return Response(
            {
                "message": (
                    "Workspace list endpoint is not part "
                    "of the required API."
                )
            },
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(
            data=request.data
        )
        serializer.is_valid(raise_exception=True)

        actor = get_actor(request)
        owner = serializer.validated_data["owner"]

        if actor.id != owner.id:
            raise PermissionDenied(
                "X-User-ID must match the workspace owner."
            )

        try:
            with transaction.atomic():

                workspace = serializer.save(
                    owner=owner
                )

                WorkspaceMember.objects.create(
                    workspace=workspace,
                    user=owner,
                    role=WorkspaceMember.Role.ADMIN,
                )

        except IntegrityError as exc:
            raise PermissionDenied(
                "Workspace creation failed because owner membership could not be created."
            ) from exc

        output_serializer = self.get_serializer(
            workspace
        )

        return Response(
            output_serializer.data,
            status=status.HTTP_201_CREATED,
        )

    def retrieve(
        self,
        request,
        *args,
        **kwargs,
    ):
        workspace = self.get_object()

        require_workspace_role(
            request,
            workspace,
            {
                WorkspaceMember.Role.ADMIN,
                WorkspaceMember.Role.EDITOR,
                WorkspaceMember.Role.VIEWER,
            },
        )

        serializer = self.get_serializer(workspace)

        return Response(serializer.data)

    # -----------------------------------------------------
    # MEMBERS
    # -----------------------------------------------------

    @action(
        detail=True,
        methods=["get", "post"],
        url_path="members",
    )
    def members(self, request, pk=None):

        workspace = self.get_object()

        # GET /members/
        if request.method == "GET":

            require_workspace_role(
                request,
                workspace,
                {
                    WorkspaceMember.Role.ADMIN,
                    WorkspaceMember.Role.EDITOR,
                    WorkspaceMember.Role.VIEWER,
                },
            )

            queryset = (
                WorkspaceMember.objects
                .filter(workspace=workspace)
                .select_related(
                    "workspace",
                    "user",
                )
                .order_by("joined_at")
            )

            roles = request.query_params.get("roles")
            joined_after = request.query_params.get(
                "joined_after"
            )
            joined_before = request.query_params.get(
                "joined_before"
            )
            email_search = request.query_params.get(
                "email"
            )

            if roles:
                role_list = [
                    value.strip()
                    for value in roles.split(",")
                    if value.strip()
                ]

                queryset = queryset.filter(
                    role__in=role_list
                )

            if joined_after:
                queryset = queryset.filter(
                    joined_at__gte=joined_after
                )

            if joined_before:
                queryset = queryset.filter(
                    joined_at__lte=joined_before
                )

            if email_search:
                queryset = queryset.filter(
                    user__email__icontains=email_search
                )

            serializer = WorkspaceMemberSerializer(
                queryset,
                many=True,
            )

            return Response(serializer.data)

        # POST /members/
        actor, membership = require_workspace_role(
            request,
            workspace,
            {
                WorkspaceMember.Role.ADMIN,
            },
        )

        serializer = WorkspaceMemberSerializer(
            data=request.data
        )

        serializer.is_valid(
            raise_exception=True
        )

        try:
            with transaction.atomic():

                member = serializer.save(
                    workspace=workspace
                )

        except IntegrityError:

            return Response(
                {
                    "message": (
                        "This user is already a member "
                        "of the workspace."
                    )
                },
                status=status.HTTP_409_CONFLICT,
            )

        return Response(
            WorkspaceMemberSerializer(member).data,
            status=status.HTTP_201_CREATED,
        )

    # -----------------------------------------------------
    # SUMMARY
    # -----------------------------------------------------

    @action(
        detail=True,
        methods=["get"],
        url_path="summary",
    )
    def summary(self, request, pk=None):

        workspace = self.get_object()

        require_workspace_role(
            request,
            workspace,
            {
                WorkspaceMember.Role.ADMIN,
                WorkspaceMember.Role.EDITOR,
                WorkspaceMember.Role.VIEWER,
            },
        )

        member_stats = (
            workspace.members
            .aggregate(
                total_members=Count("id")
            )
        )

        document_stats = (
            workspace.documents
            .aggregate(
                total_documents=Count("id")
            )
        )

        documents_by_status = list(
            workspace.documents
            .values("status")
            .annotate(
                count=Count("id")
            )
            .order_by("status")
        )

        return Response(
            {
                "workspace_id": str(workspace.id),
                "workspace_name": workspace.name,
                "total_members": (
                    member_stats["total_members"]
                ),
                "total_documents": (
                    document_stats["total_documents"]
                ),
                "documents_by_status": (
                    documents_by_status
                ),
            }
        )


# =========================================================
# DOCUMENTS
# =========================================================

class DocumentViewSet(viewsets.ModelViewSet):
    serializer_class = DocumentSerializer

    # Required:
    # POST
    # PUT
    # GET list
    # custom versions/stats/tags
    http_method_names = [
        "get",
        "post",
        "put",
    ]

    def get_queryset(self):

        queryset = (
            Document.objects
            .select_related(
                "workspace",
                "created_by",
            )
            .prefetch_related("tags")
            .order_by("-updated_at")
        )

        workspace_id = (
            self.request.query_params.get(
                "workspace"
            )
        )

        status_value = (
            self.request.query_params.get(
                "status"
            )
        )

        statuses = (
            self.request.query_params.get(
                "statuses"
            )
        )

        search = (
            self.request.query_params.get(
                "search"
            )
        )

        updated_after = (
            self.request.query_params.get(
                "updated_after"
            )
        )

        updated_before = (
            self.request.query_params.get(
                "updated_before"
            )
        )

        tag_names = (
            self.request.query_params.get(
                "tags"
            )
        )

        if workspace_id:
            queryset = queryset.filter(
                workspace_id=workspace_id
            )

        if status_value:
            queryset = queryset.filter(
                status=status_value
            )

        if statuses:
            status_list = [
                value.strip()
                for value in statuses.split(",")
                if value.strip()
            ]

            queryset = queryset.filter(
                status__in=status_list
            )

        if updated_after:
            queryset = queryset.filter(
                updated_at__gte=updated_after
            )

        if updated_before:
            queryset = queryset.filter(
                updated_at__lte=updated_before
            )

        if tag_names:

            tag_list = [
                value.strip()
                for value in tag_names.split(",")
                if value.strip()
            ]

            queryset = (
                queryset
                .filter(
                    tags__name__in=tag_list
                )
                .distinct()
            )

        # REQUIRED Q OBJECT SEARCH
        if search:

            queryset = queryset.filter(
                Q(
                    title__icontains=search
                )
                |
                Q(
                    content__icontains=search
                )
            )

        return queryset

    def list(
        self,
        request,
        *args,
        **kwargs,
    ):

        actor = get_actor(request)

        queryset = self.get_queryset()

        member_workspace_ids = (
            WorkspaceMember.objects
            .filter(user=actor)
            .values_list(
                "workspace_id",
                flat=True,
            )
        )

        queryset = queryset.filter(
            workspace_id__in=member_workspace_ids
        )

        serializer = self.get_serializer(
            queryset,
            many=True,
        )

        return Response(serializer.data)

    def retrieve(
        self,
        request,
        *args,
        **kwargs,
    ):
        return Response(
            {
                "message": (
                    "Document detail endpoint is not part "
                    "of the required 17 APIs."
                )
            },
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    # -----------------------------------------------------
    # CREATE DOCUMENT + VERSION
    # -----------------------------------------------------

    def create(
        self,
        request,
        *args,
        **kwargs,
    ):

        actor = get_actor(request)

        serializer = self.get_serializer(
            data=request.data
        )

        serializer.is_valid(
            raise_exception=True
        )

        workspace = (
            serializer.validated_data[
                "workspace"
            ]
        )

        require_workspace_role(
            request,
            workspace,
            {
                WorkspaceMember.Role.ADMIN,
                WorkspaceMember.Role.EDITOR,
            },
        )

        with transaction.atomic():

            document = serializer.save(
                created_by=actor
            )

            version_number = (
                document.versions.count() + 1
            )

            DocumentVersion.objects.create(
                document=document,
                content=document.content,
                version_number=version_number,
                saved_by=actor,
            )

        return Response(
            self.get_serializer(document).data,
            status=status.HTTP_201_CREATED,
        )

    # -----------------------------------------------------
    # UPDATE DOCUMENT + VERSION
    # -----------------------------------------------------

    def update(
        self,
        request,
        *args,
        **kwargs,
    ):

        actor = get_actor(request)

        try:
            document = (
                Document.objects
                .select_related(
                    "workspace",
                    "created_by",
                )
                .get(
                    pk=kwargs["pk"]
                )
            )
        except Document.DoesNotExist:
            return Response(
                {
                    "message": "Document not found."
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        require_workspace_role(
            request,
            document.workspace,
            {
                WorkspaceMember.Role.ADMIN,
                WorkspaceMember.Role.EDITOR,
            },
        )

        serializer = self.get_serializer(
            document,
            data=request.data,
        )

        serializer.is_valid(
            raise_exception=True
        )

        with transaction.atomic():

            document = serializer.save()

            version_number = (
                document.versions.count() + 1
            )

            DocumentVersion.objects.create(
                document=document,
                content=document.content,
                version_number=version_number,
                saved_by=actor,
            )

        return Response(
            self.get_serializer(document).data,
            status=status.HTTP_200_OK,
        )

    # -----------------------------------------------------
    # VERSIONS
    # -----------------------------------------------------

    @action(
        detail=True,
        methods=["get"],
        url_path="versions",
    )
    def versions(
        self,
        request,
        pk=None,
    ):

        try:
            document = (
                Document.objects
                .select_related(
                    "workspace",
                    "created_by",
                )
                .get(pk=pk)
            )
        except Document.DoesNotExist:
            return Response(
                {
                    "message": "Document not found."
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        require_workspace_role(
            request,
            document.workspace,
            {
                WorkspaceMember.Role.ADMIN,
                WorkspaceMember.Role.EDITOR,
                WorkspaceMember.Role.VIEWER,
            },
        )

        versions = (
            DocumentVersion.objects
            .filter(document=document)
            .select_related(
                "document",
                "saved_by",
            )
            .order_by("-version_number")
        )

        serializer = (
            DocumentVersionSerializer(
                versions,
                many=True,
            )
        )

        return Response(serializer.data)

    # -----------------------------------------------------
    # STATS
    # -----------------------------------------------------

    @action(
        detail=True,
        methods=["get"],
        url_path="stats",
    )
    def stats(
        self,
        request,
        pk=None,
    ):

        try:
            document = (
                Document.objects
                .select_related(
                    "workspace",
                    "created_by",
                )
                .get(pk=pk)
            )
        except Document.DoesNotExist:
            return Response(
                {
                    "message": "Document not found."
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        require_workspace_role(
            request,
            document.workspace,
            {
                WorkspaceMember.Role.ADMIN,
                WorkspaceMember.Role.EDITOR,
                WorkspaceMember.Role.VIEWER,
            },
        )

        version_count = (
            document.versions
            .aggregate(
                total=Count("id")
            )["total"]
        )

        comment_count = (
            document.comments
            .aggregate(
                total=Count("id")
            )["total"]
        )

        contributor_ids = (
            document.versions
            .values_list(
                "saved_by_id",
                flat=True,
            )
            .distinct()
        )

        contributor_count = (
            contributor_ids.count()
        )

        return Response(
            {
                "document_id": str(
                    document.id
                ),
                "title": document.title,
                "version_count": version_count,
                "comment_count": comment_count,
                "contributor_count": contributor_count,
            }
        )

    # -----------------------------------------------------
    # TAGS
    # -----------------------------------------------------

    @action(
        detail=True,
        methods=["post"],
        url_path="tags",
    )
    def add_tags(
        self,
        request,
        pk=None,
    ):

        try:
            document = (
                Document.objects
                .select_related(
                    "workspace"
                )
                .get(pk=pk)
            )
        except Document.DoesNotExist:
            return Response(
                {
                    "message": "Document not found."
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        require_workspace_role(
            request,
            document.workspace,
            {
                WorkspaceMember.Role.ADMIN,
                WorkspaceMember.Role.EDITOR,
            },
        )

        serializer = (
            DocumentTagSerializer(
                data=request.data
            )
        )

        serializer.is_valid(
            raise_exception=True
        )

        tag_ids = (
            serializer.validated_data[
                "tag_ids"
            ]
        )

        tags = Tag.objects.filter(
            id__in=tag_ids
        )

        found_ids = set(
            tags.values_list(
                "id",
                flat=True,
            )
        )

        missing_ids = [
            str(tag_id)
            for tag_id in tag_ids
            if tag_id not in found_ids
        ]

        if missing_ids:
            return Response(
                {
                    "message": (
                        "One or more tag IDs are invalid."
                    ),
                    "invalid_tag_ids": missing_ids,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        for tag in tags:
            tag.documents.add(document)

        return Response(
            {
                "message": (
                    f"{tags.count()} tag(s) "
                    "attached to document."
                )
            },
            status=status.HTTP_200_OK,
        )


# =========================================================
# COMMENTS
# =========================================================

class CommentViewSet(viewsets.ModelViewSet):
    serializer_class = CommentSerializer

    http_method_names = [
        "get",
        "post",
    ]

    def retrieve(
        self,
        request,
        *args,
        **kwargs,
    ):
        return Response(
            {
                "message": (
                    "Comment detail endpoint is not part "
                    "of the required 17 APIs."
                )
            },
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def get_queryset(self):

        queryset = (
            Comment.objects
            .select_related(
                "document",
                "author",
                "parent",
            )
            .prefetch_related(
                "replies__author",
            )
            .order_by("created_at")
        )

        document_id = (
            self.request.query_params.get(
                "document"
            )
        )

        if document_id:

            queryset = queryset.filter(
                document_id=document_id,
                parent__isnull=True,
            )

        return queryset

    def create(
        self,
        request,
        *args,
        **kwargs,
    ):

        serializer = self.get_serializer(
            data=request.data
        )

        serializer.is_valid(
            raise_exception=True
        )

        actor = get_actor(request)

        document = (
            serializer.validated_data[
                "document"
            ]
        )

        require_workspace_role(
            request,
            document.workspace,
            {
                WorkspaceMember.Role.ADMIN,
                WorkspaceMember.Role.EDITOR,
                WorkspaceMember.Role.VIEWER,
            },
        )

        comment = serializer.save(
            author=actor
        )

        return Response(
            self.get_serializer(comment).data,
            status=status.HTTP_201_CREATED,
        )

    def list(
        self,
        request,
        *args,
        **kwargs,
    ):

        document_id = (
            request.query_params.get(
                "document"
            )
        )

        if not document_id:
            return Response(
                {
                    "message": (
                        "The document query parameter "
                        "is required."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            document = (
                Document.objects
                .select_related("workspace")
                .get(pk=document_id)
            )
        except Document.DoesNotExist:
            return Response(
                {
                    "message": "Document not found."
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        require_workspace_role(
            request,
            document.workspace,
            {
                WorkspaceMember.Role.ADMIN,
                WorkspaceMember.Role.EDITOR,
                WorkspaceMember.Role.VIEWER,
            },
        )

        serializer = self.get_serializer(
            self.get_queryset(),
            many=True,
        )

        return Response(serializer.data)


# =========================================================
# TAGS
# =========================================================

class TagViewSet(viewsets.ModelViewSet):
    queryset = Tag.objects.all().order_by("name")
    serializer_class = TagSerializer

    http_method_names = ["post"]

    def create(
        self,
        request,
        *args,
        **kwargs,
    ):

        serializer = self.get_serializer(
            data=request.data
        )

        serializer.is_valid(
            raise_exception=True
        )

        try:
            tag = serializer.save()
        except IntegrityError:

            return Response(
                {
                    "message": (
                        "A tag with this name already exists."
                    )
                },
                status=status.HTTP_409_CONFLICT,
            )

        return Response(
            self.get_serializer(tag).data,
            status=status.HTTP_201_CREATED,
        )


# =========================================================
# AUDIT LOGS
# =========================================================

class AuditLogViewSet(viewsets.ModelViewSet):
    serializer_class = AuditLogSerializer

    http_method_names = ["get"]

    def retrieve(
        self,
        request,
        *args,
        **kwargs,
    ):
        return Response(
            {
                "message": (
                    "Audit log detail endpoint is not part "
                    "of the required 17 APIs."
                )
            },
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def get_queryset(self):

        queryset = (
            AuditLog.objects
            .select_related("actor")
            .order_by("-timestamp")
        )

        actions = (
            self.request.query_params.get(
                "actions"
            )
        )

        model_name = (
            self.request.query_params.get(
                "model_name"
            )
        )

        timestamp_after = (
            self.request.query_params.get(
                "timestamp_after"
            )
        )

        timestamp_before = (
            self.request.query_params.get(
                "timestamp_before"
            )
        )

        if actions:

            action_list = [
                value.strip()
                for value in actions.split(",")
                if value.strip()
            ]

            queryset = queryset.filter(
                action__in=action_list
            )

        if model_name:
            queryset = queryset.filter(
                model_name__icontains=model_name
            )

        if timestamp_after:
            queryset = queryset.filter(
                timestamp__gte=timestamp_after
            )

        if timestamp_before:
            queryset = queryset.filter(
                timestamp__lte=timestamp_before
            )

        return queryset

    def list(
        self,
        request,
        *args,
        **kwargs,
    ):

        actor = get_actor(request)

        is_admin = (
            WorkspaceMember.objects
            .filter(
                user=actor,
                role=WorkspaceMember.Role.ADMIN,
            )
            .exists()
        )

        if not is_admin:
            raise PermissionDenied(
                "Only workspace administrators can view audit logs."
            )

        serializer = self.get_serializer(
            self.get_queryset(),
            many=True,
        )

        return Response(serializer.data)