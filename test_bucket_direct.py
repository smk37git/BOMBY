#!/usr/bin/env python
"""
Test script to directly interact with Google Cloud Storage bucket without Django.
"""

import os
from pathlib import Path
import logging
from google.cloud import storage
from google.oauth2 import service_account

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_bucket_direct():
    """Test direct interaction with Google Cloud Storage bucket."""
    BASE_DIR = Path(__file__).resolve().parent
    bucket_name = 'bomby-user-uploads'
    project_id = 'premium-botany-453018-a0'
    
    # Load credentials
    credentials_path = os.path.join(BASE_DIR, 'gcs-credentials.json')
    if not os.path.exists(credentials_path):
        logger.error(f"Credentials file not found: {credentials_path}")
        return False
    
    try:
        # Initialize storage client with explicit credentials
        credentials = service_account.Credentials.from_service_account_file(
            credentials_path,
            scopes=['https://www.googleapis.com/auth/devstorage.read_write']
        )
        client = storage.Client(
            credentials=credentials,
            project=project_id
        )
        
        logger.info(f"Successfully created storage client for project: {project_id}")
        
        # Get the bucket
        try:
            bucket = client.get_bucket(bucket_name)
            logger.info(f"Successfully accessed bucket: {bucket.name}")
            
            # Try to upload a test file
            test_blob = bucket.blob('test_direct_upload.txt')
            test_blob.upload_from_string('Testing direct upload to bucket')
            logger.info("Successfully uploaded test file")
            
            # Make the blob public
            test_blob.make_public()
            logger.info(f"File is publicly accessible at: {test_blob.public_url}")
            
            # Read the file back
            content = test_blob.download_as_string()
            logger.info(f"Successfully read file content: {content}")
            
            # List all blobs in the bucket
            logger.info("Listing all files in bucket:")
            blobs = bucket.list_blobs()
            for blob in blobs:
                logger.info(f"- {blob.name} ({blob.size} bytes)")
            
            # Clean up
            test_blob.delete()
            logger.info("Successfully deleted test file")
            
            return True
            
        except Exception as e:
            logger.error(f"Error accessing bucket: {str(e)}")
            return False
            
    except Exception as e:
        logger.error(f"Error initializing storage client: {str(e)}")
        return False

if __name__ == "__main__":
    success = test_bucket_direct()
    if success:
        logger.info("Direct bucket test completed successfully!")
    else:
        logger.error("Direct bucket test failed!") 