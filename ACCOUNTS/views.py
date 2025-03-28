from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, get_user_model
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib import messages
from django.views.generic import ListView, DetailView, UpdateView
from .forms import CustomUserCreationForm, ProfileEditForm, UsernameEditForm
from .models import User
from django.conf import settings
from PIL import Image
from .moderation import moderate_image_content
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse
from django.contrib.auth.views import PasswordResetView
from django.contrib.auth.forms import PasswordResetForm
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.contrib.sites.shortcuts import get_current_site
from django.contrib.auth.tokens import default_token_generator
from django.urls import reverse_lazy
from django.db.models import Q, Max, Count
from .models import Message, Conversation
from .forms import MessageForm
from STORE.models import Order
from django.utils import timezone
import json
import io
import boto3
from django.core.management import call_command
import os
from django.core.paginator import Paginator
from .decorators import admin_required
from datetime import datetime, timedelta

# Signup Form
def signup(request):
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            # Specify the backend for authentication
            username = form.cleaned_data.get('username')
            raw_password = form.cleaned_data.get('password1')
            user = authenticate(request=request, 
                              username=username, 
                              password=raw_password,
                              backend='django.contrib.auth.backends.ModelBackend')
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            return redirect('ACCOUNTS:account')
    else:
        form = CustomUserCreationForm()
    return render(request, 'ACCOUNTS/signup.html', {'form': form})

@login_required
def account(request):

    # Get user's orders
    user_orders = Order.objects.filter(user=request.user).order_by('-created_at')
    
    return render(request, 'ACCOUNTS/account.html', {
        'user_orders': user_orders
    })

class AdminRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_admin_user()

class ClientRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_client() or self.request.user.is_admin_user()

@login_required
def purchase_history(request):
    # Get all orders for the current user
    user_orders = Order.objects.filter(user=request.user).order_by('-created_at')
    
    # Mark Stream Store purchases differently in the template
    for order in user_orders:
        if order.product.id == 4:
            order.is_access_product = True
        else:
            order.is_access_product = False
    
    return render(request, 'ACCOUNTS/purchase_history.html', {
        'user_orders': user_orders
    })

# Profile View
User = get_user_model()
def profile_view(request, username=None):
    # If username provided, show that specific user's profile
    if username:
        profile_user = get_object_or_404(User, username=username)
    # If no username and user is logged in, show their profile
    elif request.user.is_authenticated:
        profile_user = request.user
    else:
        # Redirect to login if no username provided and not logged in
        return redirect('ACCOUNTS:login')
    
    context = {
        'profile_user': profile_user,
        'is_own_profile': request.user == profile_user
    }
    return render(request, 'ACCOUNTS/profile.html', context)

# Edit Profile Picture
@login_required
def edit_profile(request):
    profile_pic_error = False
    
    if request.method == 'POST':
        form = ProfileEditForm(request.POST, request.FILES, instance=request.user)
        
        # Track if profile picture was changed
        profile_pic_changed = False
        
        # Handle profile picture clearing
        if request.POST.get('clear_picture') == 'true':
            if request.user.profile_picture:
                # Delete the existing profile picture
                request.user.profile_picture.delete(save=False)
                request.user.profile_picture = None
                profile_pic_changed = True
        
        # Validate profile picture if uploaded
        profile_picture = request.FILES.get('profile_picture')
        if profile_picture:
            profile_pic_changed = True
            # Check file type
            valid_types = ['image/jpeg', 'image/png', 'image/gif']
            if hasattr(profile_picture, 'content_type') and profile_picture.content_type not in valid_types:
                form.add_error('profile_picture', 'Invalid file type. Please upload a JPEG, PNG, or GIF image.')
                messages.error(request, 'Invalid file type. Please upload a JPEG, PNG, or GIF image.')
                profile_pic_error = True
            
            # Check file size (10MB max)
            if profile_picture.size > 10 * 1024 * 1024:
                form.add_error('profile_picture', 'Image size must be less than 10MB.')
                messages.error(request, 'Image size must be less than 10MB.')
                profile_pic_error = True
            
            # Content moderation
            is_safe, explicit_categories = moderate_image_content(profile_picture)
            if not is_safe:
                categories_str = ", ".join(explicit_categories)
                error_msg = f'Image contains inappropriate content and cannot be used. Detected: {categories_str}'
                form.add_error('profile_picture', error_msg)
                messages.error(request, error_msg)
                profile_pic_error = True
        
        if form.is_valid():
            user = form.save()
            # Add success message based on what was updated
            if profile_pic_changed:
                messages.success(request, 'Profile picture updated successfully!')
            else:
                messages.success(request, 'Profile updated successfully!')
            return redirect('ACCOUNTS:edit_profile')
    else:
        form = ProfileEditForm(instance=request.user)
    
    # Include the error flag in the context
    return render(request, 'ACCOUNTS/edit_profile.html', {
        'form': form,
        'profile_pic_error': profile_pic_error
    })

    
@login_required
def edit_username(request, user_id=None):
    # If no user_id is provided, use the current logged-in user
    if user_id is None:
        user = request.user
        form_class = UsernameEditForm
        template = 'ACCOUNTS/edit_username.html'
        redirect_url = 'ACCOUNTS:account'
    else:
        # Admin editing another user's username
        user = get_object_or_404(User, id=user_id)
        form_class = UsernameEditForm
        template = 'ACCOUNTS/admin_edit_username.html'
        redirect_url = 'ACCOUNTS:user_management'

    if request.method == 'POST':
        form = form_class(request.POST, instance=user)
        if form.is_valid():
            form.save()
            return redirect(redirect_url)
    else:
        form = form_class(instance=user)
    
    return render(request, template, {
        'form': form,
        'user_being_edited': user
    })

# Custom Password Reset
class CustomPasswordResetForm(PasswordResetForm):
    def send_mail(self, subject_template_name, email_template_name, 
                  context, from_email, to_email, html_email_template_name=None):
        """
        Override the default send_mail to use our styled HTML template
        """
        subject = "Password Reset Request - BOMBY"
        
        # Render the custom HTML template
        html_email = render_to_string('ACCOUNTS/emails/password_reset_email.html', context)
        
        # Create and send email with HTML content
        email_message = EmailMultiAlternatives(subject, '', from_email, [to_email])
        email_message.attach_alternative(html_email, 'text/html')
        email_message.send()
    
    def save(self, domain_override=None,
             subject_template_name='registration/password_reset_subject.txt',
             email_template_name='registration/password_reset_email.html',
             use_https=False, token_generator=default_token_generator,
             from_email=None, request=None, html_email_template_name=None,
             extra_email_context=None):
        """
        Override the default save method to use our custom email template
        """
        email = self.cleaned_data["email"]
        active_users = self.get_users(email)
        
        for user in active_users:
            if not domain_override:
                current_site = get_current_site(request)
                site_name = current_site.name
                domain = current_site.domain
            else:
                site_name = domain = domain_override
            
            user_email = user.email
            context = {
                'email': user_email,
                'domain': domain,
                'site_name': site_name,
                'uid': urlsafe_base64_encode(force_bytes(user.pk)),
                'user': user,
                'token': token_generator.make_token(user),
                'protocol': 'https' if use_https else 'http',
                **(extra_email_context or {}),
            }
            
            self.send_mail(
                subject_template_name, email_template_name, context, from_email,
                user_email, html_email_template_name=html_email_template_name,
            )

class CustomPasswordResetView(PasswordResetView):
    """
    Custom password reset view that uses our styled email template
    """
    form_class = CustomPasswordResetForm
    success_url = reverse_lazy('ACCOUNTS:password_reset_done')
    email_template_name = 'registration/password_reset_email.html'
    template_name = 'ACCOUNTS/password_reset.html'

# Promotional Wall
def promotional_wall(request):
    """View to display users organized by user type"""
    try:
        # Initialize context first
        context = {}
        
        # Get users by type - with error checks
        admin_users = User.objects.filter(user_type=User.UserType.ADMIN).order_by('username')
        client_users = User.objects.filter(user_type=User.UserType.CLIENT).order_by('username')
        supporter_users = User.objects.filter(user_type=User.UserType.SUPPORTER).order_by('username')
        member_users = User.objects.filter(user_type=User.UserType.MEMBER).order_by('username')
        
        # Add to context
        context = {
            'admin_users': admin_users,
            'client_users': client_users,
            'supporter_users': supporter_users,
            'member_users': member_users,
        }
        
        return render(request, 'ACCOUNTS/promotional_wall.html', context)
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"Error in promotional_wall: {error_details}")
        return HttpResponse(f"Server Error: {str(e)}", status=500)

@login_required
def update_promo_links(request):
    if request.method == 'POST':
        promo_links = request.POST.getlist('promo_links')
        
        # Allow 0-2 links
        if len(promo_links) <= 2:
            request.user.promo_links = promo_links
            request.user.save()
        else:
            messages.error(request, 'Please select up to 2 social links for the promotional wall.')
    
    return redirect('ACCOUNTS:account')

# Messaging System
@login_required
def inbox(request):
    # Get all conversations for the current user
    conversations = Conversation.objects.filter(
        participants=request.user
    ).order_by('-updated_at')
    
    # Count unread messages for each conversation
    for conversation in conversations:
        conversation.unread_count = Message.objects.filter(
            sender__in=conversation.participants.exclude(id=request.user.id),
            recipient=request.user,
            is_read=False,
            conversation=conversation
        ).count()
    
    # Count total unread messages
    unread_count = Message.objects.filter(
        recipient=request.user,
        is_read=False
    ).count()
    
    return render(request, 'ACCOUNTS/inbox.html', {
        'conversations': conversations,
        'unread_count': unread_count
    })

@login_required
def conversation(request, user_id):
    other_user = get_object_or_404(User, id=user_id)
    
    # Get or create conversation between current user and other user
    conversation = Conversation.objects.filter(
        participants=request.user
    ).filter(
        participants=other_user
    ).first()
    
    if not conversation:
        conversation = Conversation.objects.create()
        conversation.participants.add(request.user, other_user)
        conversation.save()
    
    # Get all conversations for the sidebar
    conversations = Conversation.objects.filter(
        participants=request.user
    ).prefetch_related('participants').order_by('-updated_at')
    
    # Count unread messages for each conversation
    for conv in conversations:
        conv.unread_count = Message.objects.filter(
            sender__in=conv.participants.exclude(id=request.user.id),
            recipient=request.user,
            is_read=False,
            conversation=conv
        ).count()
    
    # Get all messages in this conversation
    message_list = Message.objects.filter(
        Q(sender=request.user, recipient=other_user) | 
        Q(sender=other_user, recipient=request.user)
    ).select_related('sender', 'recipient').order_by('created_at')
    
    # Ensure timezone aware datetimes
    for msg in message_list:
        if timezone.is_naive(msg.created_at):
            msg.created_at = timezone.make_aware(msg.created_at)
    
    # Mark messages as read
    unread_messages = message_list.filter(recipient=request.user, is_read=False)
    for message in unread_messages:
        message.is_read = True
        message.save()
    
    # Handle new message
    if request.method == 'POST':
        form = MessageForm(request.POST)
        if form.is_valid():
            message = form.save(commit=False)
            message.sender = request.user
            message.recipient = other_user
            message.conversation = conversation
            message.save()
            
            # Update conversation's last_message
            conversation.last_message = message
            conversation.save()
            
            return redirect('ACCOUNTS:conversation', user_id=user_id)
    else:
        form = MessageForm()
    
    # Getting Django messages (success, error, etc.) to differentiate from chat messages
    django_messages = list(messages.get_messages(request))
    
    return render(request, 'ACCOUNTS/conversation.html', {
        'conversation': conversation,
        'conversations': conversations,
        'messages': message_list,
        'other_user': other_user,
        'form': form,
        'django_messages': django_messages
    })

@login_required
def send_message(request, user_id):
    if request.method == 'POST':
        recipient = get_object_or_404(User, id=user_id)
        content = request.POST.get('content', '').strip()
        
        if content:
            try:
                # Import the validator directly
                from .validators import validate_clean_content
                from django.core.exceptions import ValidationError
                
                # Validate content for profanity
                try:
                    content = validate_clean_content(content)
                except ValidationError as e:
                    print(f"PROFANITY ERROR: {str(e)}")
                    # For AJAX requests
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse({
                            'status': 'error',
                            'message': str(e)
                        }, status=400)  # Use 400 status code for validation errors
                    
                    # For regular form submissions
                    messages.error(request, str(e))
                    return redirect('ACCOUNTS:conversation', user_id=user_id)
                
                # Get or create conversation
                conversation = Conversation.objects.filter(
                    participants=request.user
                ).filter(
                    participants=recipient
                ).first()
                
                if not conversation:
                    conversation = Conversation.objects.create()
                    conversation.participants.add(request.user, recipient)
                    conversation.save()
                
                # Create message
                message = Message.objects.create(
                    sender=request.user,
                    recipient=recipient,
                    content=content,
                    conversation=conversation
                )
                
                # Update conversation's last_message
                conversation.last_message = message
                conversation.save()
                
                # Handle AJAX requests
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'status': 'success',
                        'message_id': message.id,
                        'timestamp': message.created_at.isoformat()
                    })
                
                return redirect('ACCOUNTS:conversation', user_id=user_id)
                
            except Exception as e:
                # Log the error for debugging
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Error in send_message: {str(e)}")
                
                # For AJAX requests
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'status': 'error',
                        'message': "Could not send message. Please try again."
                    }, status=500)
                
                # For regular form submissions
                messages.error(request, "Could not send message. Please try again.")
                return redirect('ACCOUNTS:conversation', user_id=user_id)
        
        # Empty message
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'status': 'error',
                'message': "Message cannot be empty."
            }, status=400)
        
        messages.error(request, "Message cannot be empty.")
        return redirect('ACCOUNTS:conversation', user_id=user_id)
    
    return redirect('ACCOUNTS:inbox')

@login_required
def get_unread_count(request):
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        unread_count = Message.objects.filter(
            recipient=request.user,
            is_read=False
        ).count()
        return JsonResponse({'unread_count': unread_count})
    return JsonResponse({'error': 'Invalid request'}, status=400)

# Check for unread messages for emails
@csrf_exempt
def run_message_check(request):
    # Get token from request
    request_token = request.headers.get('X-API-Key')
    
    # Get actual token from environment
    actual_token = os.environ.get('SCHEDULER_API_KEY')
    
    # Validate token
    if not request_token or request_token != actual_token:
        return HttpResponse("Unauthorized", status=401)
        
    if request.method == 'POST':
        # Run regular message check
        call_command('check_unread_messages')
        
        # Import and run order message check for all users
        from STORE.unread_messages_email import send_unread_order_messages_email
        from django.contrib.auth import get_user_model
        
        User = get_user_model()
        users = User.objects.filter(email__isnull=False).exclude(email='')
        
        for user in users:
            try:
                send_unread_order_messages_email(request, user)
            except Exception as e:
                print(f"Error sending order message emails for {user.username}: {e}")
        
        return HttpResponse("Commands executed successfully", status=200)
    return HttpResponse("Method not allowed", status=405)

# Function to link order messages with the user messaging system
@login_required
def copy_order_message_to_inbox(request, order_id, message_id):
    """Copy an order message to the user messaging system"""
    from STORE.models import OrderMessage
    
    order = get_object_or_404(Order, id=order_id)
    order_message = get_object_or_404(OrderMessage, id=message_id, order=order)
    
    # Determine recipient (the other user in the order conversation)
    if request.user == order.user:
        recipient = order_message.sender
    else:
        recipient = order.user
    
    # Get or create conversation
    conversation = Conversation.objects.filter(
        participants=request.user
    ).filter(
        participants=recipient
    ).first()
    
    if not conversation:
        conversation = Conversation.objects.create()
        conversation.participants.add(request.user, recipient)
        conversation.save()
    
    # Create message in the user messaging system
    message = Message.objects.create(
        sender=request.user,
        recipient=recipient,
        content=f"Regarding Order #{order.id}: {order_message.message}",
        conversation=conversation,
        related_order=order
    )
    
    # Update conversation's last_message
    conversation.last_message = message
    conversation.save()
    
    return redirect('ACCOUNTS:conversation', user_id=recipient.id)

@login_required
def user_search(request):
    """View to search for users to start a conversation with"""
    query = request.GET.get('q', '')
    
    if query:
        # Search for users by username
        users = User.objects.filter(
            username__icontains=query
        ).exclude(id=request.user.id)[:20]  # Limit to 20 results
    else:
        users = []
    
    return render(request, 'ACCOUNTS/user_search.html', {
        'users': users,
        'query': query
    })

@login_required
def start_conversation(request, user_id):
    """Start a new conversation with a user"""
    other_user = get_object_or_404(User, id=user_id)
    
    # Check if conversation already exists
    conversation = Conversation.objects.filter(
        participants=request.user
    ).filter(
        participants=other_user
    ).first()
    
    # If no conversation exists, create one
    if not conversation:
        conversation = Conversation.objects.create()
        conversation.participants.add(request.user, other_user)
        conversation.save()
    
    return redirect('ACCOUNTS:conversation', user_id=user_id)

# Admin View User Management
def is_admin(user):
    return user.is_admin_user

@login_required
@user_passes_test(is_admin)
def user_management(request):
    """View for admin users to manage all users"""
    
    # Get query parameter for search
    search_query = request.GET.get('search', '')
    
    # Filter users based on search query
    if search_query:
        users = User.objects.filter(
            username__icontains=search_query
        ) | User.objects.filter(
            email__icontains=search_query
        )
    else:
        users = User.objects.all()
    
    # Order users by date joined
    users = users.order_by('-date_joined')
    
    context = {
        'users': users,
        'search_query': search_query,
    }
    
    return render(request, 'ACCOUNTS/user_management.html', context)

# Select Users for Control
@login_required
@user_passes_test(is_admin)
def bulk_change_user_type(request):
    if request.method == 'POST':
        selected_users = request.POST.get('selected_users', '').split(',')
        user_type = request.POST.get('user_type')
        
        if selected_users and user_type:
            User.objects.filter(id__in=selected_users).update(user_type=user_type)
            messages.success(request, f"Updated {len(selected_users)} users to {user_type.lower()} type.")
    
    return redirect('ACCOUNTS:user_management')

@login_required
@user_passes_test(is_admin)
def bulk_delete_users(request):
    if request.method == 'POST':
        selected_users = request.POST.get('selected_users', '').split(',')
        
        if selected_users:
            deleted_count = User.objects.filter(id__in=selected_users).delete()[0]
            messages.success(request, f"Successfully deleted {deleted_count} users.")
    
    return redirect('ACCOUNTS:user_management')

# Message Monitoring
@login_required
@user_passes_test(is_admin)
def message_monitor(request):
    """Admin view to monitor all user messages"""
    
    # Get filter parameters
    start_date_str = request.GET.get('start_date', '')
    end_date_str = request.GET.get('end_date', '')
    user_filter = request.GET.get('user_filter', '')
    content_filter = request.GET.get('content_filter', '')
    read_status = request.GET.get('read_status', 'all')
    
    # Parse dates
    try:
        if start_date_str:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        else:
            # Default to 7 days ago
            start_date = datetime.now() - timedelta(days=7)
            
        if end_date_str:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
            # Make end_date inclusive by setting it to end of day
            end_date = end_date.replace(hour=23, minute=59, second=59)
        else:
            # Default to today
            end_date = datetime.now()
    except ValueError:
        # If date parsing fails, use default values
        start_date = datetime.now() - timedelta(days=7)
        end_date = datetime.now()
    
    # Start with all messages
    messages_query = Message.objects.select_related('sender', 'recipient', 'conversation').all()
    
    # Apply date filters
    messages_query = messages_query.filter(created_at__range=[start_date, end_date])
    
    # Apply user filter
    if user_filter:
        messages_query = messages_query.filter(
            Q(sender__username__icontains=user_filter) | 
            Q(recipient__username__icontains=user_filter)
        )
    
    # Apply content filter
    if content_filter:
        messages_query = messages_query.filter(content__icontains=content_filter)
    
    # Apply read status filter
    if read_status == 'read':
        messages_query = messages_query.filter(is_read=True)
    elif read_status == 'unread':
        messages_query = messages_query.filter(is_read=False)
    
    # Order by most recent first
    messages_query = messages_query.order_by('-created_at')
    
    # Paginate results
    paginator = Paginator(messages_query, 50)  # Show 50 messages per page
    page = request.GET.get('page')
    messages_list = paginator.get_page(page)
    
    context = {
        'messages_list': messages_list,
        'start_date': start_date,
        'end_date': end_date,
        'user_filter': user_filter,
        'content_filter': content_filter,
        'read_status': read_status,
    }
    
    return render(request, 'ACCOUNTS/message_monitor.html', context)

@login_required
@user_passes_test(is_admin)
def mark_message_read(request):
    """AJAX endpoint to mark a message as read"""
    if request.method == 'POST':
        message_id = request.GET.get('message_id')
        if not message_id:
            return JsonResponse({'success': False, 'error': 'No message ID provided'})
        
        try:
            message = Message.objects.get(id=message_id)
            message.is_read = True
            message.save()
            return JsonResponse({'success': True})
        except Message.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Message not found'})
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'})

@login_required
@user_passes_test(is_admin)
def delete_messages(request):
    """Endpoint to delete messages"""
    if request.method == 'POST':
        selected_messages = request.POST.get('selected_messages', '').split(',')
        
        if selected_messages and selected_messages[0]:  # Check if not empty string
            deleted_count = Message.objects.filter(id__in=selected_messages).delete()[0]
            messages.success(request, f"Successfully deleted {deleted_count} message(s).")
        else:
            messages.error(request, "No messages selected for deletion.")
    
    return redirect('ACCOUNTS:message_monitor')