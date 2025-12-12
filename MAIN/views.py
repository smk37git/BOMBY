from django.shortcuts import render, redirect, get_object_or_404
from django.core.mail import send_mail
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from .decorators import admin_required
from ACCOUNTS.models import Message
from STORE.models import Order, Product, Review
from MAIN.decorators import *
from .models import Announcement
from django.conf import settings
from django.core.mail import EmailMessage
import requests
from .decorators import admin_code_required

# Easter Egg Discount Code
import json
import random
import string
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from STORE.models import DiscountCode


# Homepage View
def home(request):
    return render(request, 'MAIN/home.html')

# About View
def about(request):
    return render(request, 'MAIN/about.html')

def contact(request):
    if request.method == 'POST':
        # Verify Turnstile
        turnstile_response = request.POST.get('cf-turnstile-response')
        verify_url = 'https://challenges.cloudflare.com/turnstile/v0/siteverify'
        verify_data = {
            'secret': settings.CLOUDFLARE_TURNSTILE_SECRET_KEY,
            'response': turnstile_response,
        }
        verify_result = requests.post(verify_url, data=verify_data).json()
        
        if not verify_result.get('success'):
            messages.error(request, 'CAPTCHA verification failed. Please try again.')
            return render(request, 'MAIN/contact.html', {'TURNSTILE_SITE_KEY': settings.CLOUDFLARE_TURNSTILE_SITE_KEY})
        
        # Rest of your existing code...
        name = request.POST.get('name')
        email = request.POST.get('email')
        subject = request.POST.get('subject')
        message = request.POST.get('message')
        
        try:
            email_message = f"""
            From: {name}
            Email: {email}
            Subject: {subject}

            Message:
            {message}
            """
            email_obj = EmailMessage(
                subject=f'BOMBY Contact: {subject}',
                body=email_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[settings.DEFAULT_FROM_EMAIL],
                reply_to=[email],
            )
            email_obj.send()
            messages.success(request, 'Your message was sent successfully!')
        except Exception as e:
            messages.error(request, f'There was an error sending your message: {str(e)}')
    
    return render(request, 'MAIN/contact.html', {'TURNSTILE_SITE_KEY': settings.CLOUDFLARE_TURNSTILE_SITE_KEY})

# Portfolio View
def portfolio(request):
    return render(request, 'PORTFOLIO/portfolio.html')

# Admin Panel View
@login_required
@admin_required
def admin_code_verify(request):
    if request.method == 'POST':
        code = request.POST.get('admin_code')
        
        if code == getattr(settings, 'ADMIN_VERIFICATION_CODE'):
            request.session['admin_code_verified'] = True
            
            redirect_url = request.session.pop('admin_redirect_url', None)
            return redirect(redirect_url or 'MAIN:admin_panel')
    
    return render(request, 'MAIN/admin_code_verify.html')

def clear_admin_session(request):
    request.session.pop('admin_code_verified', None)

@login_required
@admin_code_required
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

# Announcement Views
@login_required
@admin_code_required
def manage_announcements(request):
    if request.method == 'POST':
        message = request.POST.get('message')
        link = request.POST.get('link')
        link_text = request.POST.get('link_text')
        bg_color = request.POST.get('bg_color')
        text_color = request.POST.get('text_color')
        is_active = request.POST.get('is_active') == 'on'
        
        # Create new announcement
        Announcement.objects.create(
            message=message,
            link=link,
            link_text=link_text,
            bg_color=bg_color,
            text_color=text_color,
            is_active=is_active
        )
        
        messages.success(request, 'Announcement created successfully!')
        return redirect('MAIN:manage_announcements')
    
    announcements = Announcement.objects.all().order_by('-is_active', '-created_at')
    return render(request, 'MAIN/announcements.html', {'announcements': announcements})

@login_required
@admin_code_required
def edit_announcement(request, announcement_id):
    announcement = get_object_or_404(Announcement, id=announcement_id)
    
    if request.method == 'POST':
        announcement.message = request.POST.get('message')
        announcement.link = request.POST.get('link')
        announcement.link_text = request.POST.get('link_text')
        announcement.bg_color = request.POST.get('bg_color')
        announcement.text_color = request.POST.get('text_color')
        announcement.is_active = request.POST.get('is_active') == 'on'
        announcement.save()
        
        messages.success(request, 'Announcement updated successfully!')
        return redirect('MAIN:manage_announcements')
    
    announcements = Announcement.objects.all().order_by('-is_active', '-created_at')
    return render(request, 'MAIN/announcements.html', {
        'announcements': announcements,
        'editing': announcement
    })

@login_required
@admin_code_required
def toggle_announcement(request, announcement_id):
    announcement = get_object_or_404(Announcement, id=announcement_id)
    announcement.is_active = not announcement.is_active
    announcement.save()
    
    status = 'activated' if announcement.is_active else 'deactivated'
    messages.success(request, f'Announcement {status} successfully!')
    return redirect('MAIN:manage_announcements')

@login_required
@admin_code_required
def delete_announcement(request, announcement_id):
    announcement = get_object_or_404(Announcement, id=announcement_id)
    announcement.delete()
    
    messages.success(request, 'Announcement deleted successfully!')
    return redirect('MAIN:manage_announcements')

# Helper function to get active announcement for display in the base template
def get_active_announcement():
    try:
        return Announcement.objects.filter(is_active=True).latest('created_at')
    except Announcement.DoesNotExist:
        return None

# Easter Egg
def easter_egg(request):
    return render(request, 'MAIN/minesweeper.html')

@require_POST
@login_required
def generate_discount_code(request):
    """Generate a discount code when user wins the Minesweeper game"""
    user = request.user
    
    # Check if user already has an unused discount code
    existing_code = DiscountCode.objects.filter(user=user, is_used=False).first()
    if existing_code:
        return JsonResponse({
            'success': True,
            'code': existing_code.code
        })
    
    # Check if user has used a discount code before (from any source)
    has_used_discount = DiscountCode.objects.filter(user=user, is_used=True).exists()
    if has_used_discount:
        return JsonResponse({
            'success': False,
            'message': 'You have already used a discount code previously.'
        })
    
    # Generate a random code
    code_chars = string.ascii_uppercase + string.digits
    code = 'WIN' + ''.join(random.choice(code_chars) for _ in range(7))
    
    # Create the discount code
    discount = DiscountCode.objects.create(
        code=code,
        user=user,
        percentage=10,
        source='minesweeper'
    )
    
    return JsonResponse({
        'success': True,
        'code': code
    })

# Terms & Conditions
def terms(request):
    return render(request, 'MAIN/terms.html')

# Privacy Policy
def privacy(request):
    return render(request, 'MAIN/privacy.html')

# Error Handling
def custom_500(request):
    return render(request, 'MAIN/500.html', status=500)

def custom_403(request, exception=None):
    return render(request, 'MAIN/403.html', status=403)