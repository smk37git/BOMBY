#!/bin/bash

# Exit on error
set -e

# Configuration
PROJECT_ID="your-gcp-project-id"  # Replace with your GCP project ID

# Enable Secret Manager API
echo "Enabling Secret Manager API..."
gcloud services enable secretmanager.googleapis.com --project $PROJECT_ID

# Create secrets
echo "Creating secrets..."

# Django Secret Key
if [ -z "$DJANGO_SECRET_KEY" ]; then
  # Generate a random secret key if not provided
  DJANGO_SECRET_KEY=$(python -c 'import secrets; print(secrets.token_urlsafe(50))')
fi

echo "Creating Django secret key..."
echo -n "$DJANGO_SECRET_KEY" | gcloud secrets create django-secret \
  --replication-policy="automatic" \
  --data-file=- \
  --project $PROJECT_ID

# Database Password
if [ -z "$DB_PASSWORD" ]; then
  # Prompt for database password if not provided
  read -sp "Enter database password: " DB_PASSWORD
  echo
fi

echo "Creating database password secret..."
echo -n "$DB_PASSWORD" | gcloud secrets create db-password \
  --replication-policy="automatic" \
  --data-file=- \
  --project $PROJECT_ID

# Grant access to the Cloud Run service account
echo "Granting access to the Cloud Run service account..."
SERVICE_ACCOUNT="$(gcloud iam service-accounts list --filter="displayName:Cloud Run Service Agent" --format='value(email)' --project $PROJECT_ID)"

gcloud secrets add-iam-policy-binding django-secret \
  --member="serviceAccount:$SERVICE_ACCOUNT" \
  --role="roles/secretmanager.secretAccessor" \
  --project $PROJECT_ID

gcloud secrets add-iam-policy-binding db-password \
  --member="serviceAccount:$SERVICE_ACCOUNT" \
  --role="roles/secretmanager.secretAccessor" \
  --project $PROJECT_ID

echo "Secret Manager setup completed!" 