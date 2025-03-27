from django.template.loader import render_to_string

def generate_invoice_html(order):
    """Generate HTML invoice for an order"""
    context = {
        'order': order,
        'invoice_number': f"INV-{order.created_at.year}-{order.created_at.month:02d}-{order.id}"
    }
    
    return render_to_string('STORE/emails/invoice_email.html', context)