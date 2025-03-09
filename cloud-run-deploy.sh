#!/bin/bash

# Exit on any error
set -e

# Configuration
PROJECT_ID="premium-botany-453018-a0"
SERVICE_NAME="bomby-website"
REGION="us-central1"
IMAGE_NAME="gcr.io/$PROJECT_ID/$SERVICE_NAME"

# Apply database migrations
echo "Apply database migrations"
python manage.py migrate

# Build the Docker image
echo "Building Docker image..."
docker build -t $IMAGE_NAME .

# Configure Docker to use gcloud as a credential helper
echo "Configuring Docker authentication..."
gcloud auth configure-docker

# Push the image to Google Container Registry
echo "Pushing image to Google Container Registry..."
docker push $IMAGE_NAME

# Deploy to Cloud Run
echo "Deploying to Cloud Run..."
gcloud run deploy $SERVICE_NAME \
  --image $IMAGE_NAME \
  --platform managed \
  --region $REGION \
  --allow-unauthenticated \
  --set-env-vars="DEBUG=False,ALLOWED_HOSTS=.run.app,$SERVICE_NAME.run.app,SENDGRID_API_KEY=your-sendgrid-api-key,AWS_REGION=us-east-1,ENABLE_IMAGE_MODERATION=False,IMAGE_MODERATION_CONFIDENCE_THRESHOLD=85.0" \
  --set-secrets="DJANGO_SECRET_KEY=django-secret-key:latest,AWS_ACCESS_KEY_ID=aws-access-key:latest,AWS_SECRET_ACCESS_KEY=aws-secret-key:latest" \
  --memory 512Mi

echo "Deployment complete! Your website should be available soon at the URL above."