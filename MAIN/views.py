from django.shortcuts import render, redirect
from django.core.mail import send_mail
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from .decorators import admin_required
from ACCOUNTS.models import Message
from STORE.models import Order, Product, Review
from MAIN.decorators import *

# Create your views here.

# Homepage View
def home(request):
    return render(request, 'MAIN/home.html')

# About View
def about(request):
    return render(request, 'MAIN/about.html')

# Contact View
def contact(request):
    if request.method == 'POST':
        # Extract form data
        name = request.POST.get('name')
        email = request.POST.get('email')
        subject = request.POST.get('subject')
        message = request.POST.get('message')
        
        try:
            # Compose email
            email_message = f"""
            From: {name}
            Email: {email}
            Subject: {subject}

            Message:
            {message}
            """
            # Send email
            send_mail(
                f'New Message: {subject}',  # Email subject
                email_message,
                'your-gmail@gmail.com',  # From email
                ['sebetvbusiness@gmail.com'],  # To email
                fail_silently=False,
            )
            
            # Add success message
            messages.success(request, 'Your message was sent successfully!')
        
        except Exception as e:
            # Add error message
            messages.error(request, 'There was an error sending your message. Please try again.')
    
    return render(request, 'MAIN/contact.html')

# Portfolio View
def portfolio(request):
    return render(request, 'PORTFOLIO/portfolio.html')

# Admin Panel View
@login_required
@admin_required
def admin_panel(request):
    User = get_user_model()
    
    # Get statistics
    user_count = User.objects.count()
    order_count = Order.objects.count()
    unread_message_count = Message.objects.filter(is_read=False).count()
    product_count = Product.objects.count()
    
    context = {
        'user_count': user_count,
        'order_count': order_count,
        'unread_message_count': unread_message_count,
        'product_count': product_count,
    }
    
    return render(request, 'MAIN/admin_panel.html', context)

# Coming Soon View
def coming_soon(request):
    return render(request, 'MAIN/coming_soon.html')