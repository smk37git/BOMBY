# Add this to a new file called moderation.py in your app directory

import boto3
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

def moderate_image_content(image_file):
    """
    Uses AWS Rekognition to detect inappropriate content in images
    Returns (is_safe, categories) tuple
    is_safe: Boolean indicating if the image is appropriate
    categories: List of detected inappropriate categories if any
    """
    # Skip moderation if disabled in settings
    if not settings.ENABLE_IMAGE_MODERATION:
        return True, []
    
    # Check if AWS credentials are configured
    if not settings.AWS_ACCESS_KEY_ID or not settings.AWS_SECRET_ACCESS_KEY:
        logger.warning("AWS credentials not configured. Image moderation skipped.")
        return True, []
    
    try:
        # Create boto3 client
        client = boto3.client(
            'rekognition',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_REGION
        )
        
        # Read image bytes
        image_file.seek(0)
        image_bytes = image_file.read()
        image_file.seek(0)  # Reset file pointer
        
        # Detect moderation labels
        response = client.detect_moderation_labels(
            Image={'Bytes': image_bytes},
            MinConfidence=50  # Get all results above 50% confidence
        )
        
        # Check for explicit categories with confidence above threshold
        explicit_categories = []
        threshold = settings.IMAGE_MODERATION_CONFIDENCE_THRESHOLD
        
        for label in response['ModerationLabels']:
            if label['Confidence'] > threshold:
                explicit_categories.append(f"{label['Name']} ({label['Confidence']:.1f}%)")
        
        is_safe = len(explicit_categories) == 0
        return is_safe, explicit_categories
    
    except Exception as e:
        logger.error(f"Error in content moderation: {str(e)}")
        # Default to allowing the image if the service fails
        return True, []