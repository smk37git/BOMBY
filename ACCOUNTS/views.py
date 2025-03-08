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
import io
import boto3

# Import Firestore functions
from .firebase import create_firebase_user, update_firebase_user, get_firebase_user, delete_firebase_user

# Signup Form
def signup(request):
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            
            # Create user in Firestore
            user_data = {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'user_type': user.user_type,
                'promo_links': user.promo_links
            }
            create_firebase_user(user_data)
            
            login(request, user)
            return redirect('ACCOUNTS:account')
    else:
        form = CustomUserCreationForm()
    return render(request, 'ACCOUNTS/signup.html', {'form': form})

@login_required
def account(request):
    # You can get Firestore data for additional info if needed
    # firebase_user_data = get_firebase_user(request.user.id)
    return render(request, 'ACCOUNTS/account.html')

class AdminRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_admin_user()

class ClientRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_client() or self.request.user.is_admin_user()

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
    
    # Get additional data from Firestore if needed
    # firebase_user_data = get_firebase_user(profile_user.id)
    
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
            
            # Update user in Firestore
            profile_pic_url = user.profile_picture.url if user.profile_picture else ""
            update_data = {
                'username': user.username,
                'profile_picture_url': profile_pic_url,
                'promo_links': user.promo_links
            }
            update_firebase_user(user.id, update_data)
            
            # Add success message based on what was updated
            if profile_pic_changed:
                messages.success(request, 'Profile picture updated successfully!')
            else:
                messages.success(request, 'Profile updated successfully!')
            return redirect('ACCOUNTS:edit_profile')
    else:
        form = ProfileEditForm(instance=request.user)
    
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
            user = form.save()
            
            # Update username in Firestore
            update_firebase_user(user.id, {'username': user.username})
            
            return redirect(redirect_url)
    else:
        form = form_class(instance=user)
    
    return render(request, template, {
        'form': form,
        'user_being_edited': user
    })

# Promotional Wall
def promotional_wall(request):
    """View to display users organized by user type"""
    
    # Get users by type
    admin_users = User.objects.filter(user_type=User.UserType.ADMIN).order_by('username')
    client_users = User.objects.filter(user_type=User.UserType.CLIENT).order_by('username')
    supporter_users = User.objects.filter(user_type=User.UserType.SUPPORTER).order_by('username')
    member_users = User.objects.filter(user_type=User.UserType.MEMBER).order_by('username')
    
    context = {
        'admin_users': admin_users,
        'client_users': client_users,
        'supporter_users': supporter_users,
        'member_users': member_users,
    }
    
    return render(request, 'ACCOUNTS/promotional_wall.html', context)

@login_required
def update_promo_links(request):
    if request.method == 'POST':
        promo_links = request.POST.getlist('promo_links')
        
        # Allow 0-2 links
        if len(promo_links) <= 2:
            request.user.promo_links = promo_links
            request.user.save()
            
            # Update in Firestore
            update_firebase_user(request.user.id, {'promo_links': promo_links})
            
        else:
            messages.error(request, 'Please select up to 2 social links for the promotional wall.')
    
    return redirect('ACCOUNTS:account')

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
            # Update in Django DB
            User.objects.filter(id__in=selected_users).update(user_type=user_type)
            
            # Update each user in Firestore
            for user_id in selected_users:
                update_firebase_user(user_id, {'user_type': user_type})
                
            messages.success(request, f"Updated {len(selected_users)} users to {user_type.lower()} type.")
    
    return redirect('ACCOUNTS:user_management')

@login_required
@user_passes_test(is_admin)
def bulk_delete_users(request):
    if request.method == 'POST':
        selected_users = request.POST.get('selected_users', '').split(',')
        
        if selected_users:
            # Delete from Firebase first
            for user_id in selected_users:
                delete_firebase_user(user_id)
                
            # Then delete from Django DB
            deleted_count = User.objects.filter(id__in=selected_users).delete()[0]
            messages.success(request, f"Successfully deleted {deleted_count} users.")
    
    return redirect('ACCOUNTS:user_management')