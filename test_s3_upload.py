#!/usr/bin/env python
"""
Test script to directly upload a file to S3 without using Django.
This helps isolate if the issue is with Django or with S3 configuration.
"""

import os
import boto3
import logging
from botocore.exceptions import ClientError

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_s3_upload():
    """Test direct upload to S3 bucket."""
    # Get AWS credentials from environment variables
    aws_access_key_id = os.environ.get('AWS_ACCESS_KEY_ID')
    aws_secret_access_key = os.environ.get('AWS_SECRET_ACCESS_KEY')
    aws_region = os.environ.get('AWS_REGION', 'us-east-2')
    bucket_name = os.environ.get('AWS_S3_BUCKET_NAME', 'bomby-user-uploads')
    
    if not aws_access_key_id or not aws_secret_access_key:
        logger.error("AWS credentials not found in environment variables")
        return False
    
    try:
        # Create S3 client
        s3_client = boto3.client(
            's3',
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            region_name=aws_region
        )
        
        logger.info(f"Created S3 client for region: {aws_region}")
        
        # Create a test file
        test_file_path = 'test_upload.txt'
        with open(test_file_path, 'w') as f:
            f.write('This is a test file for S3 upload')
        
        # Upload the file
        object_key = 'test_direct_upload.txt'
        try:
            s3_client.upload_file(test_file_path, bucket_name, object_key)
            logger.info(f"Successfully uploaded {test_file_path} to {bucket_name}/{object_key}")
            
            # Generate a URL for the uploaded file
            url = f"https://{bucket_name}.s3.{aws_region}.amazonaws.com/{object_key}"
            logger.info(f"File should be accessible at: {url}")
            
            # Clean up the local test file
            os.remove(test_file_path)
            
            return True
        except ClientError as e:
            logger.error(f"Error uploading file: {str(e)}")
            return False
    except Exception as e:
        logger.error(f"Error in S3 test: {str(e)}")
        return False

if __name__ == "__main__":
    success = test_s3_upload()
    if success:
        logger.info("S3 upload test completed successfully!")
    else:
        logger.error("S3 upload test failed!") 