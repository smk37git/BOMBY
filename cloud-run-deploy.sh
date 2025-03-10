#!/bin/bash

# Exit on any error
set -e

# Configuration
PROJECT_ID="premium-botany-453018-a0"
SERVICE_NAME="bomby-website"
REGION="us-central1"
IMAGE_NAME="gcr.io/$PROJECT_ID/$SERVICE_NAME"
INSTANCE_CONNECTION_NAME="$PROJECT_ID:$REGION:bomby-database"
DB_NAME="postgres"
DB_USER="postgres"
DB_PASSWORD=$(grep DB_PASSWORD .env | cut -d'=' -f2)
SENDGRID_KEY=$(grep SENDGRID_API_KEY .env | cut -d'=' -f2)
DEFAULT_FROM_EMAIL=$(grep DEFAULT_FROM_EMAIL .env | cut -d'=' -f2)

# Build the Docker image
echo "Building Docker image..."
docker build -t $IMAGE_NAME .

# Configure Docker to use gcloud as a credential helper
echo "Configuring Docker authentication..."
gcloud auth configure-docker

# Push the image to Google Container Registry
echo "Pushing image to Google Container Registry..."
docker push $IMAGE_NAME

# Upload secrets if not already there
echo "Ensuring secrets exist..."
gcloud secrets describe django-secret-key > /dev/null 2>&1 || \
gcloud secrets create django-secret-key --replication-policy="automatic"

# Add DB password to Secret Manager if not already there
gcloud secrets describe postgres-password > /dev/null 2>&1 || \
gcloud secrets create postgres-password --replication-policy="automatic" --data-file=<(echo -n "$DB_PASSWORD")

# Deploy to Cloud Run
echo "Deploying to Cloud Run..."
gcloud run deploy $SERVICE_NAME \
  --image $IMAGE_NAME \
  --platform managed \
  --region $REGION \
  --allow-unauthenticated \
  --set-env-vars="DEBUG=False,\
ALLOWED_HOSTS=.run.app,$SERVICE_NAME.run.app,\
SENDGRID_API_KEY=$SENDGRID_KEY,\
DEFAULT_FROM_EMAIL=$DEFAULT_FROM_EMAIL,\
SENDGRID_SANDBOX_MODE=False,\
DB_NAME=$DB_NAME,\
DB_USER=$DB_USER,\
DB_HOST=/cloudsql/$INSTANCE_CONNECTION_NAME,\
  --set-secrets="DJANGO_SECRET_KEY=django-secret-key:latest,\
DB_PASSWORD=postgres-password:latest,\
AWS_ACCESS_KEY_ID=aws-access-key:latest,\
AWS_SECRET_ACCESS_KEY=aws-secret-key:latest" \
  --memory 512Mi \
  --add-cloudsql-instances=$INSTANCE_CONNECTION_NAME

echo "Deployment complete! Your website should be available soon at the URL above."