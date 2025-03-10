"""
Script to check AWS credentials in the environment.
This is for local development only.
"""

import os
import sys

# Check for AWS credentials
aws_access_key = os.environ.get('AWS_ACCESS_KEY_ID')
aws_secret_key = os.environ.get('AWS_SECRET_ACCESS_KEY')
aws_bucket = os.environ.get('AWS_S3_BUCKET_NAME')
aws_region = os.environ.get('AWS_REGION')

if not aws_access_key or not aws_secret_key:
    print("WARNING: AWS credentials not found in environment variables!")
    print("S3 storage will not work correctly.")
    print("Please set the following environment variables:")
    print("  - AWS_ACCESS_KEY_ID")
    print("  - AWS_SECRET_ACCESS_KEY")
    print("  - AWS_S3_BUCKET_NAME")
    print("  - AWS_REGION")
    sys.exit(1)
else:
    print(f"AWS credentials found. Using bucket: {aws_bucket}")
    print("AWS environment variables are correctly set.") 