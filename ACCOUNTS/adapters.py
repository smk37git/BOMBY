from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.account.utils import user_username
from django.contrib.auth import get_user_model
import logging

logger = logging.getLogger(__name__)
User = get_user_model()

class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        """Handle user login/signup via social accounts"""
        if not sociallogin.email_addresses:
            return
        
        email = sociallogin.email_addresses[0].email.lower()
        
        # If social account already exists and is linked, let allauth handle it
        if sociallogin.is_existing:
            return
        
        # Check if a user with this email already exists
        try:
            existing_user = User.objects.get(email__iexact=email)
            # Connect social account to existing user - allauth handles the login
            sociallogin.connect(request, existing_user)
        except User.DoesNotExist:
            pass
        except Exception as e:
            logger.error(f"Error in pre_social_login: {e}")
    
    def populate_user(self, request, sociallogin, data):
        """Generate unique username for new users"""
        user = super().populate_user(request, sociallogin, data)
        
        if not user.username:
            email = data.get('email', '')
            email_base = email.split('@')[0] if email else 'user'
            base_username = ''.join(c for c in email_base if c.isalnum())
            
            username = base_username
            counter = 1
            while User.objects.filter(username=username).exists():
                username = f"{base_username}{counter}"
                counter += 1
            
            user.username = username
        
        return user