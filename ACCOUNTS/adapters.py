from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.account.adapter import DefaultAccountAdapter
from django.conf import settings
from django.shortcuts import redirect

class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        """
        Invoked just after a user successfully authenticates via a social provider,
        but before the login is actually processed.
        """
        # Get the user from the sociallogin object
        user = sociallogin.user

        # Check if user already exists in the system
        if user.id:
            # User exists, just proceed with login
            return
            
        # This is a new user, set default values
        user.user_type = user.UserType.MEMBER
        
    def populate_user(self, request, sociallogin, data):
        """Customize user creation from social account data"""
        user = super().populate_user(request, sociallogin, data)
        user.user_type = user.UserType.MEMBER
        return user
        
    def get_connect_redirect_url(self, request, socialaccount):
        """Override to redirect to your custom URL after connecting"""
        return settings.LOGIN_REDIRECT_URL
        
class CustomAccountAdapter(DefaultAccountAdapter):
    def get_login_redirect_url(self, request):
        """Where to redirect after successful login"""
        return settings.LOGIN_REDIRECT_URL