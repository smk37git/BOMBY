from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.account.utils import user_username, user_email, user_field, perform_login
from django.contrib.auth import get_user_model

User = get_user_model()

class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        """Handle user login/signup via social accounts"""
        # Get user data from the social account
        user = sociallogin.user
        
        # If the user already exists, just connect the account
        if user.id or sociallogin.is_existing:
            return
            
        # Check if a user with this email already exists
        try:
            existing_user = User.objects.get(email__iexact=user.email)
            # Connect the social account to the existing user
            sociallogin.connect(request, existing_user)
            # Perform login with the existing account
            perform_login(request, existing_user, email_verification='none')
        except User.DoesNotExist:
            # Generate a username if none exists
            if not user_username(user):
                email_base = user_email(user).split('@')[0]
                # Clean the username and ensure uniqueness
                base_username = ''.join(c for c in email_base if c.isalnum())
                username = base_username
                counter = 1
                while User.objects.filter(username=username).exists():
                    username = f"{base_username}{counter}"
                    counter += 1
                user_username(user, username)