#!/usr/bin/env python
"""
Test script to verify Google Cloud Storage connection and upload capabilities.
Run this script to check if your GCS configuration is working properly.
"""

import os
import sys
import django
from pathlib import Path
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add the project directory to the Python path
BASE_DIR = Path(__file__).resolve().parent
sys.path.append(str(BASE_DIR))

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mywebsite.settings')
django.setup()

from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.conf import settings

def test_gcs_connection():
    """Test connection to Google Cloud Storage and upload a test file."""
    logger.info("Testing Google Cloud Storage connection...")
    
    # Log GCS settings
    logger.info(f"GS_BUCKET_NAME: {settings.GS_BUCKET_NAME}")
    logger.info(f"GS_PROJECT_ID: {getattr(settings, 'GS_PROJECT_ID', 'Not set')}")
    logger.info(f"DEFAULT_FILE_STORAGE: {settings.DEFAULT_FILE_STORAGE}")
    logger.info(f"GS_CREDENTIALS is None: {settings.GS_CREDENTIALS is None}")
    
    # Create a test file
    test_content = b"This is a test file to verify GCS upload functionality."
    test_filename = "test_upload.txt"
    
    try:
        # Upload the test file
        path = default_storage.save(test_filename, ContentFile(test_content))
        logger.info(f"Test file uploaded successfully to: {path}")
        
        # Verify the file exists
        if default_storage.exists(path):
            logger.info(f"File exists in storage: {path}")
            
            # Get the file URL
            url = default_storage.url(path)
            logger.info(f"File URL: {url}")
            
            # Read the file content
            content = default_storage.open(path).read()
            logger.info(f"File content: {content}")
            
            # Delete the test file
            default_storage.delete(path)
            logger.info(f"Test file deleted: {path}")
            
            return True
        else:
            logger.error(f"File does not exist in storage: {path}")
            return False
    except Exception as e:
        logger.error(f"Error testing GCS connection: {str(e)}")
        return False

if __name__ == "__main__":
    success = test_gcs_connection()
    if success:
        logger.info("GCS connection test completed successfully!")
    else:
        logger.error("GCS connection test failed!") 