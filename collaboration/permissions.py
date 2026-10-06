import uuid

from django.core.exceptions import ValidationError
from rest_framework.exceptions import NotAuthenticated, NotFound, PermissionDenied

from .models import User, WorkspaceMember


def get_actor(request):
    """
    Assignment-friendly actor identification.

    The client supplies:
        X-User-ID: <user UUID>

    This is not production authentication.
    It allows the API to demonstrate role-based permissions
    without inventing an extra login endpoint.
    """

    raw_user_id = request.headers.get("X-User-ID")

    if not raw_user_id:
        raise NotAuthenticated(
            "X-User-ID header is required."
        )

    try:
        user_id = uuid.UUID(raw_user_id)
    except (ValueError, AttributeError):
        raise PermissionDenied(
            "X-User-ID must contain a valid UUID."
        )

    try:
        return User.objects.get(id=user_id)
    except User.DoesNotExist:
        raise NotFound("Actor user was not found.")


def require_workspace_role(request, workspace, allowed_roles):
    actor = get_actor(request)

    membership = (
        WorkspaceMember.objects
        .select_related("workspace", "user")
        .filter(
            workspace=workspace,
            user=actor,
        )
        .first()
    )

    if membership is None:
        raise PermissionDenied(
            "User is not a member of this workspace."
        )

    if membership.role not in allowed_roles:
        raise PermissionDenied(
            "User does not have the required workspace role."
        )

    return actor, membership