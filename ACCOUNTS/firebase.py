import firebase_admin
from firebase_admin import credentials, firestore
from django.conf import settings
import os
import logging
import sys  # Add missing import

# Set up logging
logger = logging.getLogger(__name__)

# Initialize variables
firebase_app = None
db = None
users_ref = None

try:
    # Path to service account credentials
    cred_path = os.environ.get('FIREBASE_CREDENTIALS_PATH', os.path.join(settings.BASE_DIR, 'firebase-credentials.json'))
    
    logger.info(f"Looking for Firebase credentials at: {cred_path}")
    
    if os.path.exists(cred_path):
        cred = credentials.Certificate(cred_path)
        
        # Initialize Firebase app
        firebase_app = firebase_admin.initialize_app(cred)
        
        # Get Firestore client
        db = firestore.client()
        
        # Initialize the users collection reference
        users_ref = db.collection('users')
        
        logger.info("Firebase initialized successfully")
    else:
        logger.error(f"Firebase credentials file not found at: {cred_path}")
except Exception as e:
    logger.error(f"Firebase initialization error: {str(e)}")
    print(f"Firebase database connection failed: {str(e)}", file=sys.stderr)
    # Continue without Firebase

# Helper functions for user operations
def create_firebase_user(user_data):
    """Create a new user document in Firestore"""
    try:
        if not db or not users_ref:
            logger.warning("Firebase not initialized, skipping user creation")
            return None
            
        user_ref = users_ref.document(str(user_data.get('id')))
        user_ref.set({
            'username': user_data.get('username'),
            'email': user_data.get('email'),
            'user_type': user_data.get('user_type'),
            'profile_picture_url': user_data.get('profile_picture_url', ''),
            'promo_links': user_data.get('promo_links', []),
            'date_joined': firestore.SERVER_TIMESTAMP
        })
        return user_ref
    except Exception as e:
        logger.error(f"Error creating Firebase user: {str(e)}")
        return None

def update_firebase_user(user_id, user_data):
    """Update user document in Firestore"""
    try:
        if not db or not users_ref:
            logger.warning("Firebase not initialized, skipping user update")
            return None
            
        user_ref = users_ref.document(str(user_id))
        user_ref.update(user_data)
        return user_ref
    except Exception as e:
        logger.error(f"Error updating Firebase user: {str(e)}")
        return None

def get_firebase_user(user_id):
    """Get user document from Firestore"""
    try:
        if not db or not users_ref:
            logger.warning("Firebase not initialized, skipping user retrieval")
            return {}
            
        user_ref = users_ref.document(str(user_id))
        return user_ref.get().to_dict()
    except Exception as e:
        logger.error(f"Error getting Firebase user: {str(e)}")
        return {}

def delete_firebase_user(user_id):
    """Delete user document from Firestore"""
    try:
        if not db or not users_ref:
            logger.warning("Firebase not initialized, skipping user deletion")
            return
            
        users_ref.document(str(user_id)).delete()
    except Exception as e:
        logger.error(f"Error deleting Firebase user: {str(e)}")