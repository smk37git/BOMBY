from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.account.adapter import DefaultAccountAdapter
from django.conf import settings
from django.shortcuts import redirect

class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        # Auto-connect if email exists
        if sociallogin.is_existing:
            return
            
        # Extract email from social account
        email = sociallogin.account.extra_data.get('email')
        if email:
            # Try to find existing user with this email
            try:
                user = User.objects.get(email=email)
                # Connect social account to existing user
                sociallogin.connect(request, user)
            except User.DoesNotExist:
                pass

    def save_user(self, request, sociallogin, form=None):
        user = super().save_user(request, sociallogin, form)
        user.user_type = user.UserType.MEMBER
        user.save()
        return user