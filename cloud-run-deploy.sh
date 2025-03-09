#!/bin/bash

# Exit on any error
set -e

# Configuration
PROJECT_ID="premium-botany-453018-a0"
SERVICE_NAME="bomby-website"
REGION="us-central1"
IMAGE_NAME="gcr.io/$PROJECT_ID/$SERVICE_NAME"
BUCKET_NAME="bomby-user-data"

# Create GCS bucket if it doesn't exist
echo "Ensuring GCS bucket exists..."
gsutil ls -b gs://$BUCKET_NAME > /dev/null 2>&1 || gsutil mb -l $REGION gs://$BUCKET_NAME

# Check for existing database
gsutil cp gs://$BUCKET_NAME/db.sqlite3 ./db.sqlite3 || echo "No database found in bucket"

# Build the Docker image
echo "Building Docker image..."
docker build -t $IMAGE_NAME .

# Configure Docker to use gcloud as a credential helper
echo "Configuring Docker authentication..."
gcloud auth configure-docker

# Push the image to Google Container Registry
echo "Pushing image to Google Container Registry..."
docker push $IMAGE_NAME

# Upload the service account key to Secret Manager if not already there
echo "Ensuring service account key secret exists..."
gcloud secrets describe gcs-credentials > /dev/null 2>&1 || \
gcloud secrets create gcs-credentials --data-file=database-bucket.json

# Get values from .env file
SENDGRID_KEY=$(grep SENDGRID_API_KEY .env | cut -d'=' -f2)

# Deploy to Cloud Run
echo "Deploying to Cloud Run..."
gcloud run deploy $SERVICE_NAME \
  --image $IMAGE_NAME \
  --platform managed \
  --region $REGION \
  --allow-unauthenticated \
  --set-env-vars="DEBUG=False,ALLOWED_HOSTS=.run.app,$SERVICE_NAME.run.app,SENDGRID_API_KEY=$SENDGRID_KEY,GS_BUCKET_NAME=$BUCKET_NAME,GS_PROJECT_ID=$PROJECT_ID" \
  --set-secrets="DJANGO_SECRET_KEY=django-secret-key:latest,GOOGLE_APPLICATION_CREDENTIALS=gcs-credentials:latest,AWS_ACCESS_KEY_ID=aws-access-key:latest,AWS_SECRET_ACCESS_KEY=aws-secret-key:latest" \
  --memory 512Mi

echo "Deployment complete! Your website should be available soon at the URL above."