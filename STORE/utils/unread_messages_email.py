from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.contrib.sites.shortcuts import get_current_site
from django.utils import timezone
from datetime import timedelta
from django.db import connection
from STORE.models import Order, OrderMessage

def send_unread_order_messages_email(request, user):
    """
    Send an email notification to users with unread order messages
    First after 5 minutes, then every 24 hours if still unread
    """
    # Get current time
    five_minutes_ago = timezone.now() - timedelta(minutes=5)
    last_day = timezone.now() - timedelta(days=1)
    
    unread_count = 0
    order_ids = []
    
    # Check if staff or regular user
    if user.is_staff:
        # For staff, get unread messages from clients
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT COUNT(*), array_agg(DISTINCT "STORE_ordermessage"."order_id") 
                FROM "STORE_ordermessage" 
                JOIN "ACCOUNTS_user" ON "STORE_ordermessage"."sender_id" = "ACCOUNTS_user"."id"
                WHERE "ACCOUNTS_user"."is_staff" = FALSE 
                AND "STORE_ordermessage"."is_read" = FALSE
                AND ("STORE_ordermessage"."created_at" <= %s
                    OR "STORE_ordermessage"."created_at" <= %s)
            """, [five_minutes_ago, last_day])
            result = cursor.fetchone()
            unread_count = result[0] if result[0] else 0
            order_ids = result[1] if result[1] else []
    else:
        # For regular users, get unread messages from staff
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT COUNT(*), array_agg(DISTINCT "STORE_ordermessage"."order_id")
                FROM "STORE_ordermessage"
                JOIN "ACCOUNTS_user" ON "STORE_ordermessage"."sender_id" = "ACCOUNTS_user"."id" 
                JOIN "STORE_order" ON "STORE_ordermessage"."order_id" = "STORE_order"."id"
                WHERE "ACCOUNTS_user"."is_staff" = TRUE 
                AND "STORE_ordermessage"."is_read" = FALSE 
                AND "STORE_order"."user_id" = %s
                AND ("STORE_ordermessage"."created_at" <= %s
                    OR "STORE_ordermessage"."created_at" <= %s)
            """, [user.id, five_minutes_ago, last_day])
            result = cursor.fetchone()
            unread_count = result[0] if result[0] else 0
            order_ids = result[1] if result[1] else []
    
    # If no unread messages, don't send email
    if unread_count == 0 or not order_ids:
        return
    
    # Get orders with unread messages
    orders = Order.objects.filter(id__in=order_ids)
    
    # Get current site for email template
    current_site = get_current_site(request)
    
    # Prepare context for email template
    context = {
        'user': user,
        'unread_count': unread_count,
        'order_count': len(orders),
        'orders': orders[:5],
        'domain': current_site.domain,
        'protocol': 'https' if request.is_secure() else 'http',
    }
    
    # Render the email template
    html_email = render_to_string('STORE/emails/unread_order_messages_email.html', context)
    subject = f"BOMBY: You Have {unread_count} Unread Order Message{'s' if unread_count > 1 else ''}"
    
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
        print(f"Error sending unread order messages email: {e}")
        return False