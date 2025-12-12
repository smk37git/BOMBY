from django.conf import settings
from django.core.mail import send_mail, EmailMessage
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.contrib.sites.shortcuts import get_current_site
import tempfile
import os


def get_html_class():
    """Dynamically import HTML class from WeasyPrint only when needed"""
    try:
        from weasyprint import HTML
        return HTML
    except ImportError:
        return None


def send_fuzeobs_invoice_email(request, user, purchase, plan_type):
    """Send invoice email for FuzeOBS purchase"""
    current_site = get_current_site(request)
    
    # Generate invoice number
    invoice_number = f"FOB-{purchase.created_at.year}-{purchase.created_at.month:02d}-{purchase.id}"
    
    plan_details = {
        'pro': {'name': 'FuzeOBS Pro (Monthly)', 'price': '$7.50'},
        'lifetime': {'name': 'FuzeOBS Lifetime', 'price': '$45.00'},
    }
    
    plan = plan_details.get(plan_type, {'name': 'FuzeOBS', 'price': str(purchase.amount)})
    
    context = {
        'user': user,
        'purchase': purchase,
        'invoice_number': invoice_number,
        'plan_name': plan['name'],
        'plan_price': plan['price'],
        'domain': current_site.domain,
        'protocol': 'https' if request.is_secure() else 'http',
    }
    
    subject = f"FuzeOBS: Your Invoice #{invoice_number}"
    html_message = render_to_string('FUZEOBS/emails/fuzeobs_invoice_email.html', context)
    plain_message = strip_tags(html_message)
    
    HTML = get_html_class()
    
    if HTML:
        # Generate PDF with WeasyPrint
        temp = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
        HTML(string=html_message).write_pdf(temp.name)
        
        email = EmailMessage(
            subject=subject,
            body=html_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user.email]
        )
        email.content_subtype = "html"
        
        with open(temp.name, 'rb') as f:
            email.attach(f"fuzeobs_invoice_{invoice_number}.pdf", f.read(), "application/pdf")
        
        email.send(fail_silently=False)
        os.unlink(temp.name)
    else:
        # Fallback to HTML email without PDF
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message=html_message,
            fail_silently=False,
        )