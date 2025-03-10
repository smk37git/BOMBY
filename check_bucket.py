#!/usr/bin/env python
"""
Script to check if the Google Cloud Storage bucket exists and has the correct permissions.
"""

import os
import sys
from pathlib import Path
import logging
from google.cloud import storage
from google.oauth2 import service_account

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add the project directory to the Python path
BASE_DIR = Path(__file__).resolve().parent
sys.path.append(str(BASE_DIR))

def check_bucket():
    """Check if the bucket exists and has the correct permissions."""
    # Load environment variables
    bucket_name = os.environ.get('GS_BUCKET_NAME', 'bomby-user-uploads')
    project_id = os.environ.get('GS_PROJECT_ID', 'premium-botany-453018-a0')
    
    # Load credentials
    credentials_path = os.path.join(BASE_DIR, 'gcs-credentials.json')
    if not os.path.exists(credentials_path):
        logger.error(f"Credentials file not found: {credentials_path}")
        return False
    
    try:
        # Initialize storage client
        credentials = service_account.Credentials.from_service_account_file(credentials_path)
        client = storage.Client(credentials=credentials, project=project_id)
        
        # Check if bucket exists
        logger.info(f"Checking if bucket exists: {bucket_name}")
        try:
            bucket = client.get_bucket(bucket_name)
            logger.info(f"Bucket exists: {bucket.name}")
            
            # Check bucket permissions
            logger.info("Checking bucket permissions...")
            policy = bucket.get_iam_policy()
            logger.info(f"Bucket IAM policy: {policy}")
            
            # Try to create a test file
            test_blob = bucket.blob('test_permissions.txt')
            test_blob.upload_from_string('Testing bucket permissions')
            logger.info("Successfully uploaded test file to bucket")
            
            # Try to read the test file
            content = test_blob.download_as_string()
            logger.info(f"Successfully read test file from bucket: {content}")
            
            # Try to delete the test file
            test_blob.delete()
            logger.info("Successfully deleted test file from bucket")
            
            return True
        except Exception as e:
            logger.error(f"Error accessing bucket: {str(e)}")
            
            # Try to create the bucket if it doesn't exist
            logger.info(f"Attempting to create bucket: {bucket_name}")
            try:
                bucket = client.create_bucket(bucket_name, location="us-central1")
                logger.info(f"Bucket created: {bucket.name}")
                return True
            except Exception as create_error:
                logger.error(f"Error creating bucket: {str(create_error)}")
                return False
    except Exception as e:
        logger.error(f"Error initializing storage client: {str(e)}")
        return False

if __name__ == "__main__":
    success = check_bucket()
    if success:
        logger.info("Bucket check completed successfully!")
    else:
        logger.error("Bucket check failed!") 