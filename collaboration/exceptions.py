from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler


def custom_exception_handler(exc, context):
    if isinstance(exc, DjangoValidationError):
        errors = (
            exc.message_dict
            if hasattr(exc, "message_dict")
            else exc.messages
        )
        return Response(
            {
                "message": "Validation error.",
                "errors": errors,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    response = exception_handler(exc, context)

    if response is None:
        return response

    if response.status_code == 400:
        original_data = response.data

        response.data = {
            "message": "Validation error.",
            "errors": original_data,
        }

    elif response.status_code == 404:
        detail = response.data.get(
            "detail",
            "Requested resource was not found.",
        )

        response.data = {
            "message": str(detail),
        }

    elif response.status_code == 403:
        detail = response.data.get(
            "detail",
            "You do not have permission to perform this action.",
        )

        response.data = {
            "message": str(detail),
        }

    elif response.status_code == 401:
        detail = response.data.get(
            "detail",
            "Authentication information is required.",
        )

        response.data = {
            "message": str(detail),
        }

    return response