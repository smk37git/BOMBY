from django.db.models.signals import pre_save
from django.dispatch import receiver
import logging

logger = logging.getLogger(__name__)


@receiver(pre_save, sender='ACCOUNTS.User')
def increment_token_version_on_password_change(sender, instance, **kwargs):
    """Invalidate all FuzeOBS tokens when password changes."""
    if not instance.pk:
        return  # New user, skip
    try:
        old_user = sender.objects.get(pk=instance.pk)
        if old_user.password != instance.password:
            instance.fuzeobs_token_version = (old_user.fuzeobs_token_version or 0) + 1
            logger.info(f"[AUTH] Token version bumped for user {instance.pk} (password changed)")
    except sender.DoesNotExist:
        pass