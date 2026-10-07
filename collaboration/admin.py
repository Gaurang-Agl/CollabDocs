from django.contrib import admin
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

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("id", "first_name", "last_name", "email", "phone", "created_at")
    search_fields = ("first_name", "last_name", "email", "phone")

@admin.register(Workspace)
class WorkspaceAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "owner", "is_active", "created_at")
    search_fields = ("name", "owner__email")
    list_filter = ("is_active",)

@admin.register(WorkspaceMember)
class WorkspaceMemberAdmin(admin.ModelAdmin):
    list_display = ("id", "workspace", "user", "role", "joined_at")
    list_filter = ("role",)
    search_fields = ("workspace__name", "user__email")

@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "workspace", "created_by", "status", "updated_at")
    list_filter = ("status",)
    search_fields = ("title", "content")

@admin.register(DocumentVersion)
class DocumentVersionAdmin(admin.ModelAdmin):
    list_display = ("id", "document", "version_number", "saved_by", "saved_at")
    list_filter = ("version_number",)

@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ("id", "document", "author", "parent", "created_at")
    search_fields = ("content",)

@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("id", "name")
    search_fields = ("name",)

@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("id", "actor", "action", "model_name", "object_id", "timestamp")
    list_filter = ("action", "model_name")
    search_fields = ("object_id", "model_name", "action")
