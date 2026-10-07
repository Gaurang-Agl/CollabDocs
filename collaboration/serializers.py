from rest_framework import serializers

from .models import (
    User,
    Workspace,
    WorkspaceMember,
    Document,
    DocumentVersion,
    Comment,
    Tag,
    AuditLog,
)


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "id",
            "first_name",
            "last_name",
            "email",
            "phone",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "created_at",
        ]
        extra_kwargs = {
            "email": {"validators": []},
            "phone": {"validators": []},
        }

    def validate_email(self, value):
        value = value.strip().lower()

        if "@" not in value:
            raise serializers.ValidationError(
                "Enter a valid email address."
            )

        return value

    def validate_phone(self, value):
        value = value.strip()

        if not value.isdigit():
            raise serializers.ValidationError(
                "Phone must contain digits only."
            )

        if len(value) < 7:
            raise serializers.ValidationError(
                "Phone must contain at least 7 digits."
            )

        return value


class WorkspaceMemberSerializer(serializers.ModelSerializer):
    user_email = serializers.SerializerMethodField()

    class Meta:
        model = WorkspaceMember
        fields = [
            "id",
            "workspace",
            "user",
            "role",
            "joined_at",
            "user_email",
        ]
        read_only_fields = [
            "id",
            "workspace",
            "joined_at",
            "user_email",
        ]

    def get_user_email(self, obj):
        return obj.user.email if obj.user else None


class WorkspaceSerializer(serializers.ModelSerializer):
    member_count = serializers.SerializerMethodField()
    document_count = serializers.SerializerMethodField()

    class Meta:
        model = Workspace
        fields = [
            "id",
            "name",
            "owner",
            "is_active",
            "created_at",
            "member_count",
            "document_count",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "member_count",
            "document_count",
        ]

    def validate_name(self, value):
        value = value.strip()

        if not value:
            raise serializers.ValidationError(
                "Workspace name cannot be blank."
            )

        return value

    def get_member_count(self, obj):
        member_count = getattr(
            obj,
            "member_count",
            None,
        )

        if member_count is not None:
            return member_count

        return obj.members.count()

    def get_document_count(self, obj):
        document_count = getattr(
            obj,
            "document_count",
            None,
        )

        if document_count is not None:
            return document_count

        return obj.documents.count()


class DocumentSerializer(serializers.ModelSerializer):
    tags = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = [
            "id",
            "title",
            "content",
            "workspace",
            "created_by",
            "status",
            "tags",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "created_by",
            "tags",
            "updated_at",
        ]

    def validate_title(self, value):
        value = value.strip()

        if not value:
            raise serializers.ValidationError(
                "Document title cannot be blank."
            )

        return value

    def validate_workspace(self, value):
        if self.instance and self.instance.workspace_id != value.id:
            raise serializers.ValidationError(
                "Cannot change the workspace of an existing document."
            )

        if not value.is_active:
            raise serializers.ValidationError(
                "Cannot create or update a document in an inactive workspace."
            )

        return value

    def get_tags(self, obj):
        return [t.name for t in obj.tags.all()]


class DocumentVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentVersion
        fields = [
            "id",
            "document",
            "content",
            "version_number",
            "saved_by",
            "saved_at",
        ]
        read_only_fields = [
            "id",
            "version_number",
            "saved_by",
            "saved_at",
        ]


class CommentSerializer(serializers.ModelSerializer):
    replies = serializers.SerializerMethodField()

    class Meta:
        model = Comment
        fields = [
            "id",
            "document",
            "author",
            "content",
            "parent",
            "created_at",
            "replies",
        ]
        read_only_fields = [
            "id",
            "author",
            "created_at",
            "replies",
        ]

    def validate_content(self, value):
        value = value.strip()

        if not value:
            raise serializers.ValidationError(
                "Comment content cannot be blank."
            )

        return value

    def validate(self, attrs):
        parent = attrs.get("parent")
        document = attrs.get("document")

        if parent and document:
            if parent.document_id != document.id:
                raise serializers.ValidationError(
                    "Reply must be on the same document as the parent comment."
                )

        return attrs

    def get_replies(self, obj):
        if obj.parent is None:
            children = obj.replies.all()

            return CommentSerializer(
                children,
                many=True,
                context=self.context,
            ).data

        return []


class TagSerializer(serializers.ModelSerializer):
    name = serializers.CharField(
        max_length=50,
        validators=[],
    )

    class Meta:
        model = Tag
        fields = ["id", "name"]
        read_only_fields = ["id"]

    def validate_name(self, value):
        value = value.strip().lower()

        if not value:
            raise serializers.ValidationError(
                "Tag name cannot be blank."
            )

        return value


class DocumentTagSerializer(serializers.Serializer):
    tag_ids = serializers.ListField(
        child=serializers.UUIDField(),
        allow_empty=False,
    )

    def validate_tag_ids(self, value):
        if len(value) != len(set(value)):
            raise serializers.ValidationError(
                "Duplicate tag IDs are not allowed."
            )

        return value


class AuditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditLog
        fields = [
            "id",
            "actor",
            "action",
            "model_name",
            "object_id",
            "timestamp",
        ]
        read_only_fields = [
            "id",
            "actor",
            "action",
            "model_name",
            "object_id",
            "timestamp",
        ]