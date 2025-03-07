#!/bin/bash

# Exit on error
set -e

# Configuration
PROJECT_ID="your-gcp-project-id"  # Replace with your GCP project ID
SERVICE_NAME="bomby-django-app"
REGION="us-central1"  # Replace with your preferred region
IMAGE_NAME="gcr.io/$PROJECT_ID/$SERVICE_NAME"
INSTANCE_CONNECTION_NAME="$PROJECT_ID:$REGION:bomby-db-instance"  # Cloud SQL instance connection name

# Load environment variables from .env.prod
if [ -f .env.prod ]; then
  export $(grep -v '^#' .env.prod | xargs)
fi

# Build the Docker image
echo "Building Docker image..."
docker build -t $IMAGE_NAME .

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
  --memory 512Mi \
  --cpu 1 \
  --add-cloudsql-instances $INSTANCE_CONNECTION_NAME \
  --set-env-vars="DEBUG=False,ALLOWED_HOSTS=*,CLOUD_RUN=True" \
  --update-secrets="DJANGO_SECRET_KEY=django-secret:latest,DB_PASSWORD=db-password:latest" \
  --set-env-vars="DB_ENGINE=django.db.backends.postgresql,DB_NAME=$DB_NAME,DB_USER=$DB_USER,DB_HOST=/cloudsql/$INSTANCE_CONNECTION_NAME,DB_PORT=5432" \
  --project $PROJECT_ID

echo "Deployment completed!"
echo "Your application is now available at: $(gcloud run services describe $SERVICE_NAME --platform managed --region $REGION --format 'value(status.url)')" 