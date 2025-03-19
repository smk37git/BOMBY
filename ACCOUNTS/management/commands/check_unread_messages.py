from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db.models import Q
from datetime import timedelta
from django.contrib.sites.models import Site
from django.http import HttpRequest
from ACCOUNTS.models import User, Message, MessageNotification
from ACCOUNTS.utils.unread_messages_email import send_unread_messages_email

class Command(BaseCommand):
    help = 'Check for unread messages and send email notifications'

    def handle(self, *args, **options):
        # Create a mock request for the email function
        request = HttpRequest()
        request.META['SERVER_NAME'] = Site.objects.get_current().domain
        request.META['SERVER_PORT'] = '443'  # Assume HTTPS
        
        # Get users with unread messages older than 30 seconds (for testing)
        # Change back to 5 minutes for production
        thirty_seconds_ago = timezone.now() - timedelta(seconds=30)
        
        # Get distinct users who have unread messages
        users_with_unread = User.objects.filter(
            received_messages__is_read=False,
            received_messages__created_at__lte=thirty_seconds_ago
        ).distinct()
        
        # Keep track of statistics
        emails_sent = 0
        errors = 0
        skipped = 0
        
        for user in users_with_unread:
            # Skip users without email addresses
            if not user.email:
                skipped += 1
                continue
                
            # Check if we've already sent an email in the last hour
            last_hour = timezone.now() - timedelta(hours=1)
            
            # Get or create notification tracking object
            notification, created = MessageNotification.objects.get_or_create(user=user)
            
            # Skip if we've already sent an email in the last hour
            if notification.last_notified and notification.last_notified > last_hour:
                skipped += 1
                continue
            
            result = send_unread_messages_email(request, user)
            
            if result:
                # Update the last notified time
                notification.last_notified = timezone.now()
                notification.save()
                
                emails_sent += 1
                self.stdout.write(self.style.SUCCESS(f"Email sent to {user.username} ({user.email})"))
            else:
                errors += 1
                self.stdout.write(self.style.ERROR(f"Failed to send email to {user.username} ({user.email})"))
        
        self.stdout.write(self.style.SUCCESS(
            f"Process completed: {emails_sent} emails sent, {errors} errors, {skipped} skipped"
        ))