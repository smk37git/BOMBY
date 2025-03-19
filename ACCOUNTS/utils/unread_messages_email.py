from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.contrib.sites.shortcuts import get_current_site
from django.db.models import Count
from django.utils import timezone
from datetime import timedelta
from ACCOUNTS.models import Message, User

def send_unread_messages_email(request, user):
    """
    Send an email notification to users with unread messages for over 5 minutes
    """
    # Get unread messages older than 5 minutes
    five_minutes_ago = timezone.now() - timedelta(minutes=5)
    unread_messages = Message.objects.filter(
        recipient=user,
        is_read=False,
        created_at__lte=five_minutes_ago
    )
    
    # If no unread messages, don't send email
    if not unread_messages.exists():
        return
    
    # Get count of unread messages
    unread_count = unread_messages.count()
    
    # Get unique senders
    senders = User.objects.filter(
        sent_messages__in=unread_messages
    ).distinct()
    
    sender_count = senders.count()
    
    # Get current site
    current_site = get_current_site(request)
    
    # Prepare context for email template
    context = {
        'user': user,
        'unread_count': unread_count,
        'sender_count': sender_count,
        'senders': senders[:5],
        'domain': current_site.domain,
        'protocol': 'https' if request.is_secure() else 'http',
    }
    
    # Render the email template
    html_email = render_to_string('ACCOUNTS/emails/unread_messages_email.html', context)
    subject = f"You Have {unread_count} Unread Message{'s' if unread_count > 1 else ''} - BOMBY"
    
    # Send the email
    email_message = EmailMultiAlternatives(
        subject=subject,
        body='',
        from_email=None,
        to=[user.email]
    )
    email_message.attach_alternative(html_email, 'text/html')
    
    try:
        email_message.send()
        return True
    except Exception as e:
        print(f"Error sending unread messages email: {e}")
        return False