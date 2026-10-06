from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import AuditLog, Document


@receiver(post_save, sender=Document)
def document_audit_log(
    sender,
    instance,
    created,
    **kwargs,
):
    """
    Create an AuditLog whenever a Document is saved.
    """
     # Assignment explicitly requires _state.adding.
    state_was_adding = instance._state.adding

    is_created = created or state_was_adding

    action = (
        "created"
        if is_created
        else "updated"
    )

    AuditLog.objects.create(
        actor=instance.created_by,
        action=action,
        model_name="Document",
        object_id=str(instance.id),
    )