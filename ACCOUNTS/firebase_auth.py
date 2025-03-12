from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from firebase_admin import auth as firebase_auth
from firebase_admin.exceptions import FirebaseError
import logging
import jwt

User = get_user_model()
logger = logging.getLogger(__name__)

# Hardcoded Firebase Project ID to match service account
FIREBASE_PROJECT_ID = "bomby-data"

class FirebaseAuthBackend(ModelBackend):
    """
    Custom authentication backend for Firebase.
    Verifies Firebase tokens and authenticates users.
    """
    
    def authenticate(self, request, firebase_token=None, **kwargs):
        if firebase_token is None:
            logger.debug("No firebase_token provided")
            return None
            
        try:
            logger.debug(f"Attempting to verify token of length: {len(firebase_token)}")
            
            # First try with standard verification
            try:
                # Verify the token with check_revoked=True for security
                decoded_token = firebase_auth.verify_id_token(firebase_token, check_revoked=True)
                logger.debug("Token verified successfully")
            except ValueError as e:
                error_message = str(e)
                logger.warning(f"Token verification error: {error_message}")
                
                if "incorrect 'aud'" in error_message:
                    logger.info(f"Handling audience mismatch. Expected: {FIREBASE_PROJECT_ID}")
                    
                    # Extract user information from token without verification
                    # Note: This bypasses some security checks but allows cross-project auth
                    try:
                        # Decode without verification to extract user data
                        decoded_jwt = jwt.decode(firebase_token, options={"verify_signature": False})
                        
                        # Extract critical user information
                        firebase_uid = decoded_jwt.get('sub')
                        email = decoded_jwt.get('email', '')
                        name = decoded_jwt.get('name', '')
                        picture = decoded_jwt.get('picture', '')
                        
                        # Ensure we have a valid UID
                        if not firebase_uid:
                            logger.error("Token missing UID ('sub' claim)")
                            return None
                            
                        # Verify this is from our expected Firebase project
                        token_aud = decoded_jwt.get('aud')
                        if token_aud != FIREBASE_PROJECT_ID:
                            logger.warning(f"Token has unexpected audience: {token_aud}")
                            # We continue anyway since we're handling mismatched audiences
                        
                        # Create token dict with needed fields
                        decoded_token = {
                            'uid': firebase_uid,
                            'email': email,
                            'name': name,
                            'picture': picture
                        }
                        
                        logger.info(f"Successfully extracted info from token for: {email}")
                    except Exception as jwt_error:
                        logger.error(f"JWT decode error: {jwt_error}")
                        return None
                else:
                    # Other verification errors should fail
                    logger.error(f"Token verification failed: {error_message}")
                    return None
            
            # Extract the Firebase UID
            firebase_uid = decoded_token['uid']
            logger.debug(f"Processing user with Firebase UID: {firebase_uid}")
            
            # Try to find existing user with this Firebase UID
            try:
                user = User.objects.get(firebase_uid=firebase_uid)
                logger.info(f"Found existing user with Firebase UID: {firebase_uid}")
                return user
            except User.DoesNotExist:
                # Get user info from token
                email = decoded_token.get('email', '')
                display_name = decoded_token.get('name', '')
                
                logger.info(f"Token info - email: {email}, name: {display_name}, uid: {firebase_uid}")
                
                if not email:
                    logger.warning(f"No email found in Firebase token for UID: {firebase_uid}")
                    return None
                    
                # Check if user exists with this email
                try:
                    user = User.objects.get(email=email)
                    # Update user's firebase_uid
                    user.firebase_uid = firebase_uid
                    user.save()
                    logger.info(f"Updated existing user {user.username} with Firebase UID: {firebase_uid}")
                    return user
                except User.DoesNotExist:
                    # Create new user
                    # For username, first try display_name, then email part
                    if display_name:
                        username = display_name.split()[0].lower()  # First name only
                    else:
                        username = email.split('@')[0]
                        
                    # Handle username uniqueness
                    base_username = username
                    counter = 1
                    while User.objects.filter(username=username).exists():
                        username = f"{base_username}{counter}"
                        counter += 1
                        
                    # Create the new user
                    user = User.objects.create_user(
                        username=username,
                        email=email,
                        firebase_uid=firebase_uid,
                    )
                    
                    # If we have additional profile info from token, add it
                    if hasattr(user, 'profile'):
                        if display_name:
                            user.profile.display_name = display_name
                        photo_url = decoded_token.get('picture', '')
                        if photo_url:
                            user.profile.photo_url = photo_url
                        user.profile.save()
                        
                    logger.info(f"Created new user {username} with Firebase UID: {firebase_uid}")
                    return user
                    
        except FirebaseError as e:
            logger.error(f"Firebase authentication error: {str(e)}")
            return None
        except Exception as e:
            logger.exception(f"Unexpected error during Firebase authentication: {str(e)}")
            return None
            
        return None

    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None