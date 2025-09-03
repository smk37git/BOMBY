from django.contrib.auth import REDIRECT_FIELD_NAME
from django.contrib.auth.decorators import user_passes_test
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.urls import reverse

def admin_required(function=None, redirect_field_name=REDIRECT_FIELD_NAME, login_url=None):
    actual_decorator = user_passes_test(
        lambda u: u.is_authenticated and u.is_admin_user,
        login_url=login_url,
        redirect_field_name=redirect_field_name
    )
    if function:
        return actual_decorator(function)
    return actual_decorator

def admin_code_required(function=None):
    def decorator(view_func):
        def wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated or not request.user.is_admin_user:
                return redirect('ACCOUNTS:login')
            
            # Check if code was just verified for this session
            if not request.session.get('admin_code_verified'):
                request.session['admin_redirect_url'] = request.get_full_path()
                return redirect('MAIN:admin_code_verify')
            
            return view_func(request, *args, **kwargs)
        return wrapped_view
    
    if function:
        return decorator(function)
    return decorator