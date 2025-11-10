from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.account.utils import user_username, user_email, perform_login
from django.contrib.auth import get_user_model

User = get_user_model()

class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        """Handle user login/signup via social accounts"""
        user = sociallogin.user
        
        # Get the email from social account
        if not sociallogin.email_addresses:
            return
        
        email = sociallogin.email_addresses[0].email.lower()
        
        # If social account already exists, check if linked to correct user
        if sociallogin.is_existing:
            connected_user = sociallogin.account.user
            # Check if there's another user with same email
            try:
                correct_user = User.objects.get(email__iexact=email)
                if connected_user.id != correct_user.id:
                    # Unlink from wrong user and link to correct user
                    sociallogin.account.user = correct_user
                    sociallogin.account.save()
                    perform_login(request, correct_user, email_verification='none')
            except User.DoesNotExist:
                pass
            return
        
        # If user object already has ID, it's being created - check for existing user first
        if not user.id:
            try:
                existing_user = User.objects.get(email__iexact=email)
                # Connect to existing user
                sociallogin.connect(request, existing_user)
                perform_login(request, existing_user, email_verification='none')
                return
            except User.DoesNotExist:
                pass
        
        # Generate username for new user if needed
        if not user_username(user):
            email_base = email.split('@')[0]
            base_username = ''.join(c for c in email_base if c.isalnum())
            username = base_username
            counter = 1
            while User.objects.filter(username=username).exists():
                username = f"{base_username}{counter}"
                counter += 1
            user_username(user, username)