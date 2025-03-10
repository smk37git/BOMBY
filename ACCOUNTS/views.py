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
import firebase_admin
from firebase_admin import auth as firebase_auth
import json
import io
import boto3
from django.http import HttpResponse

# Add Firebase-related views here
@csrf_exempt
def firebase_login(request):
    """Handle Firebase authentication and Django login"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            id_token = data.get('idToken')
            
            # Use the custom authentication backend
            user = authenticate(request=request, firebase_token=id_token)
            
            if user:
                # Login the user to Django
                login(request, user)
                
                return JsonResponse({
                    'success': True,
                    'user': {
                        'id': user.id,
                        'username': user.username,
                        'email': user.email,
                    }
                })
            else:
                return JsonResponse({
                    'success': False,
                    'error': 'Failed to authenticate with Firebase token'
                }, status=401)
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=400)
    
    return JsonResponse({
        'success': False,
        'error': 'Method not allowed'
    }, status=405)

def firebase_config(request):
    """Return Firebase configuration for frontend use"""
    return JsonResponse({
        'apiKey': settings.FIREBASE_CONFIG['apiKey'],
        'authDomain': settings.FIREBASE_CONFIG['authDomain'],
        'projectId': settings.FIREBASE_CONFIG['projectId'],
        'storageBucket': settings.FIREBASE_CONFIG['storageBucket'],
        'messagingSenderId': settings.FIREBASE_CONFIG['messagingSenderId'],
        'appId': settings.FIREBASE_CONFIG['appId'],
    })
    
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
        
        profile_pic_changed = False
        
        # Handle profile picture clearing
        if request.POST.get('clear_picture') == 'true':
            if request.user.profile_picture:
                try:
                    # Delete the existing profile picture
                    request.user.profile_picture.delete(save=False)
                    request.user.profile_picture = None
                    profile_pic_changed = True
                except Exception as e:
                    logger.error(f"Error clearing profile picture: {str(e)}")
                    messages.error(request, 'Error clearing profile picture. Please try again.')
                    profile_pic_error = True
        
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
            
            # Check file size (5MB max)
            if profile_picture.size > 5 * 1024 * 1024:
                form.add_error('profile_picture', 'Image size must be less than 5MB.')
                messages.error(request, 'Image size must be less than 5MB.')
                profile_pic_error = True
            
            # Skip moderation in production if having issues
            try:
                is_safe, explicit_categories = moderate_image_content(profile_picture)
                if not is_safe:
                    categories_str = ", ".join(explicit_categories)
                    error_msg = f'Image contains inappropriate content and cannot be used. Detected: {categories_str}'
                    form.add_error('profile_picture', error_msg)
                    messages.error(request, error_msg)
                    profile_pic_error = True
            except Exception as e:
                logger.error(f"Moderation error: {str(e)}")
                # Continue without blocking the upload
        
        if form.is_valid():
            try:
                # Save the form without committing to get the user instance
                user = form.save(commit=False)
                
                # If a new profile picture was uploaded, process it
                if profile_picture and not profile_pic_error:
                    # Generate a unique filename to avoid caching issues
                    import uuid
                    ext = profile_picture.name.split('.')[-1]
                    unique_filename = f"profile_pictures/{uuid.uuid4().hex}.{ext}"
                    
                    # Save the profile picture with the unique filename
                    user.profile_picture.save(unique_filename, profile_picture, save=False)
                
                # Save the user instance
                user.save()
                
                if profile_pic_changed:
                    messages.success(request, 'Profile picture updated successfully!')
                else:
                    messages.success(request, 'Profile updated successfully!')
                return redirect('ACCOUNTS:edit_profile')
            except Exception as e:
                logger.error(f"Error saving profile: {str(e)}")
                messages.error(request, 'Error saving profile. Please try again.')
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
            form.save()
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