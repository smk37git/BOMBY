#!/bin/bash

# Exit on error
set -e

# Configuration
PROJECT_ID="your-gcp-project-id"  # Replace with your GCP project ID
INSTANCE_NAME="bomby-db-instance"
REGION="us-central1"  # Same region as your Cloud Run service
DB_NAME="bomby_db"
DB_USER="bomby_user"
DB_PASSWORD="your-secure-password"  # Replace with a secure password

# Create Cloud SQL PostgreSQL instance
echo "Creating Cloud SQL PostgreSQL instance..."
gcloud sql instances create $INSTANCE_NAME \
  --database-version=POSTGRES_13 \
  --cpu=1 \
  --memory=3840MiB \
  --region=$REGION \
  --root-password=$DB_PASSWORD \
  --storage-size=10GB \
  --storage-type=SSD \
  --project=$PROJECT_ID

# Create database
echo "Creating database..."
gcloud sql databases create $DB_NAME \
  --instance=$INSTANCE_NAME \
  --project=$PROJECT_ID

# Create user
echo "Creating database user..."
gcloud sql users create $DB_USER \
  --instance=$INSTANCE_NAME \
  --password=$DB_PASSWORD \
  --project=$PROJECT_ID

echo "Cloud SQL setup completed!"
echo "Instance name: $INSTANCE_NAME"
echo "Database name: $DB_NAME"
echo "Username: $DB_USER"
echo "Make sure to store your password securely and update your .env.prod file." 