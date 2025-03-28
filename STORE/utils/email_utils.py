from django.conf import settings
from django.core.mail import send_mail, EmailMessage
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.contrib.sites.shortcuts import get_current_site
import tempfile
import os
import importlib

def send_customer_email(request, order, template_name, subject):
    """Send email to customer"""
    current_site = get_current_site(request)
    context = {
        'order': order,
        'domain': current_site.domain,
        'protocol': 'https' if request.is_secure() else 'http',
    }
    
    html_message = render_to_string(f'STORE/emails/{template_name}.html', context)
    plain_message = strip_tags(html_message)
    
    send_mail(
        subject=subject,
        message=plain_message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[order.user.email],
        html_message=html_message,
        fail_silently=False,
    )

def send_admin_email(request, order, subject):
    """Send email to admin"""
    current_site = get_current_site(request)
    context = {
        'order': order,
        'domain': current_site.domain,
        'protocol': 'https' if request.is_secure() else 'http',
        'subject': subject,
    }
    
    admin_html = render_to_string('STORE/emails/admin_email.html', context)
    admin_plain = strip_tags(admin_html)
    
    send_mail(
        subject=f"[Admin] {subject} - Order #{order.id}",
        message=admin_plain,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=['sebetvbusiness@gmail.com'],
        html_message=admin_html,
        fail_silently=False,
    )

def send_pending_order_email(request, order):
    """Send pending order email to customer only"""
    subject = f"BOMBY: Complete Your Order Form for Order #{order.id}"
    send_customer_email(request, order, 'pending_order_email', subject)

def send_in_progress_order_email(request, order):
    """Send in-progress emails to both customer and admin"""
    subject = f"BOMBY: Your Order #{order.id} is Now in Progress"
    send_customer_email(request, order, 'in_progress_order_email', subject)
    send_admin_email(request, order, subject)

def send_completed_order_email(request, order):
    """Send completed emails to both customer and admin"""
    subject = f"BOMBY: Your Order #{order.id} is Complete"
    send_customer_email(request, order, 'completed_order_email', subject)
    send_admin_email(request, order, subject)

# Lazy import for WeasyPrint
def get_html_class():
    """Dynamically import HTML class from WeasyPrint only when needed"""
    try:
        from weasyprint import HTML
        return HTML
    except ImportError:
        return None

# Invoices
def send_invoice_email(request, order, invoice):
    """Send invoice email to customer"""
    current_site = get_current_site(request)
    context = {
        'order': order,
        'invoice': invoice,
        'domain': current_site.domain,
        'protocol': 'https' if request.is_secure() else 'http',
    }
    
    subject = f"BOMBY: Your Invoice #{invoice.invoice_number} for Order #{order.id}"
    html_message = render_to_string('STORE/emails/invoice_email.html', context)
    plain_message = strip_tags(html_message)
    
    # Create invoice HTML content
    from .invoice_utils import generate_invoice_html
    invoice_html = generate_invoice_html(order)
    
    # Dynamically import HTML only when needed
    HTML = get_html_class()
    
    if HTML:
        # Generate PDF with WeasyPrint
        temp = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
        HTML(string=invoice_html).write_pdf(temp.name)
        
        # Send email with PDF invoice
        email = EmailMessage(
            subject=subject,
            body=html_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[order.user.email]
        )
        email.content_subtype = "html"
        
        # Attach PDF invoice as a file
        with open(temp.name, 'rb') as f:
            email.attach(f"invoice_{invoice.invoice_number}.pdf", f.read(), "application/pdf")
        
        email.send(fail_silently=False)
        
        # Clean up temp file
        os.unlink(temp.name)
    else:
        # Fallback to HTML email without PDF attachment
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[order.user.email],
            html_message=html_message,
            fail_silently=False,
        )