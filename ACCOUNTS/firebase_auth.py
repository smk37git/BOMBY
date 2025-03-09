from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from firebase_admin import auth as firebase_auth
from firebase_admin.exceptions import FirebaseError

User = get_user_model()

class FirebaseAuthBackend(ModelBackend):
    """
    Custom authentication backend for Firebase.
    Verifies Firebase tokens and authenticates users.
    """
    
    def authenticate(self, request, firebase_token=None, **kwargs):
        if firebase_token is None:
            return None
            
        try:
            # Verify the Firebase token
            decoded_token = firebase_auth.verify_id_token(firebase_token)
            firebase_uid = decoded_token['uid']
            
            # Try to find user with this Firebase UID
            try:
                user = User.objects.get(firebase_uid=firebase_uid)
                return user
            except User.DoesNotExist:
                # Get user info from token
                email = decoded_token.get('email', '')
                
                if not email:
                    return None
                    
                # Check if user exists with this email
                try:
                    user = User.objects.get(email=email)
                    # Update user's firebase_uid
                    user.firebase_uid = firebase_uid
                    user.save()
                    return user
                except User.DoesNotExist:
                    # Create new user
                    username = email.split('@')[0]
                    # Handle username uniqueness
                    base_username = username
                    counter = 1
                    while User.objects.filter(username=username).exists():
                        username = f"{base_username}{counter}"
                        counter += 1
                        
                    user = User.objects.create_user(
                        username=username,
                        email=email,
                        firebase_uid=firebase_uid,
                    )
                    return user
                    
        except FirebaseError as e:
            # Token verification failed
            return None
            
        return None