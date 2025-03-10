#!/usr/bin/env python
"""
Script to run Django with AWS credentials.
For local development only.
"""

import os
import sys
import subprocess

# Check if AWS credentials are set
if not os.environ.get('AWS_ACCESS_KEY_ID') or not os.environ.get('AWS_SECRET_ACCESS_KEY'):
    print("AWS credentials not found in environment variables.")
    print("Please enter your AWS credentials:")
    
    # Prompt for credentials
    aws_access_key = input("AWS Access Key ID: ")
    aws_secret_key = input("AWS Secret Access Key: ")
    aws_bucket = input("AWS S3 Bucket Name [bomby-user-uploads]: ") or "bomby-user-uploads"
    aws_region = input("AWS Region [us-east-2]: ") or "us-east-2"
    
    # Set environment variables
    os.environ['AWS_ACCESS_KEY_ID'] = aws_access_key
    os.environ['AWS_SECRET_ACCESS_KEY'] = aws_secret_key
    os.environ['AWS_S3_BUCKET_NAME'] = aws_bucket
    os.environ['AWS_REGION'] = aws_region
    
    print("AWS credentials set in environment variables.")
else:
    print("Using existing AWS credentials from environment variables.")

# Run Django
if len(sys.argv) > 1:
    # Run with arguments
    command = [sys.executable, "manage.py"] + sys.argv[1:]
else:
    # Default to runserver
    command = [sys.executable, "manage.py", "runserver"]

print(f"Running command: {' '.join(command)}")
subprocess.run(command) 