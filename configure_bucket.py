#!/usr/bin/env python
"""
Script to configure Google Cloud Storage bucket permissions.
"""

import os
from pathlib import Path
import logging
from google.cloud import storage
from google.oauth2 import service_account
from google.api_core import exceptions

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def configure_bucket():
    """Configure bucket permissions and settings."""
    BASE_DIR = Path(__file__).resolve().parent
    bucket_name = 'bomby-user-uploads'
    project_id = 'premium-botany-453018-a0'
    
    # Load credentials
    credentials_path = os.path.join(BASE_DIR, 'gcs-credentials.json')
    if not os.path.exists(credentials_path):
        logger.error(f"Credentials file not found: {credentials_path}")
        return False
    
    try:
        # Initialize storage client
        credentials = service_account.Credentials.from_service_account_file(
            credentials_path,
            scopes=['https://www.googleapis.com/auth/cloud-platform']
        )
        client = storage.Client(credentials=credentials, project=project_id)
        
        # Get bucket
        try:
            bucket = client.get_bucket(bucket_name)
            logger.info(f"Found existing bucket: {bucket.name}")
            
            # Test upload with ACL
            test_blob = bucket.blob('test_permissions.txt')
            test_blob.upload_from_string('Testing bucket permissions')
            
            # Set ACL for this specific object
            test_blob.acl.all().grant_read()
            test_blob.acl.save()
            
            logger.info(f"Test file uploaded and made public: {test_blob.public_url}")
            
            # Try to read it back
            content = test_blob.download_as_string()
            logger.info(f"Successfully read back content: {content.decode()}")
            
            # Clean up
            test_blob.delete()
            logger.info("Test file deleted")
            
            # Enable CORS
            bucket.cors = [{
                'origin': ['*'],
                'method': ['GET', 'POST', 'PUT', 'DELETE', 'HEAD'],
                'responseHeader': [
                    'Content-Type',
                    'Access-Control-Allow-Origin',
                    'X-Requested-With'
                ],
                'maxAgeSeconds': 3600
            }]
            bucket.update()
            logger.info("Updated bucket CORS configuration")
            
            # Create a test directory and test file
            test_dir_blob = bucket.blob('profile_pictures/test.txt')
            test_dir_blob.upload_from_string('Testing profile_pictures directory')
            test_dir_blob.acl.all().grant_read()
            test_dir_blob.acl.save()
            logger.info("Created and configured profile_pictures directory")
            test_dir_blob.delete()
            
            return True
            
        except exceptions.NotFound:
            logger.error(f"Bucket {bucket_name} not found")
            return False
            
    except Exception as e:
        logger.error(f"Error configuring bucket: {str(e)}")
        return False

if __name__ == "__main__":
    success = configure_bucket()
    if success:
        logger.info("Bucket configuration completed successfully!")
    else:
        logger.error("Bucket configuration failed!") 