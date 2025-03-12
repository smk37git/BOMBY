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
    # Convert string settings to appropriate types
    enable_moderation = str(getattr(settings, 'ENABLE_IMAGE_MODERATION', 'False')).lower() == 'true'
    
    try:
        confidence_threshold = float(getattr(settings, 'IMAGE_MODERATION_CONFIDENCE_THRESHOLD', '99.0'))
    except (ValueError, TypeError):
        logger.warning("Invalid IMAGE_MODERATION_CONFIDENCE_THRESHOLD value, using default 99.0")
        confidence_threshold = 99.0
    
    # Skip moderation if disabled in settings
    if not enable_moderation:
        logger.info("Image moderation is disabled in settings")
        return True, []
    
    # Check if AWS credentials are configured
    aws_key = getattr(settings, 'AWS_ACCESS_KEY_ID', '')
    aws_secret = getattr(settings, 'AWS_SECRET_ACCESS_KEY', '')
    
    if not aws_key or not aws_secret:
        logger.warning("AWS credentials not configured. Image moderation skipped.")
        return True, []
    
    try:
        # Create boto3 client
        client = boto3.client(
            'rekognition',
            aws_access_key_id=aws_key,
            aws_secret_access_key=aws_secret,
            region_name=getattr(settings, 'AWS_REGION', 'us-east-1')
        )
        
        # Log successful client creation
        logger.debug("AWS Rekognition client created successfully")
        
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
        
        for label in response.get('ModerationLabels', []):
            if label.get('Confidence', 0) > confidence_threshold:
                explicit_categories.append(f"{label['Name']} ({label['Confidence']:.1f}%)")
        
        is_safe = len(explicit_categories) == 0
        
        # Log the result
        if not is_safe:
            logger.warning(f"Inappropriate content detected in image: {explicit_categories}")
        else:
            logger.debug("Image content moderation passed")
        
        return is_safe, explicit_categories
    
    except Exception as e:
        logger.error(f"Error in content moderation: {str(e)}", exc_info=True)
        # Default to allowing the image if the service fails
        return True, []