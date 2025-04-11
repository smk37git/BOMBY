#!/bin/bash

# Exit on any error
set -e

# Configuration
PROJECT_ID="premium-botany-453018-a0"
SERVICE_NAME="bomby"
REGION="us-central1"
IMAGE_NAME="gcr.io/$PROJECT_ID/$SERVICE_NAME"
INSTANCE_CONNECTION_NAME="$PROJECT_ID:$REGION:bomby-database"
BUCKET_NAME="bomby-user-uploads"

# Load secrets from .env
DB_PASSWORD=$(grep DB_PASSWORD .env | cut -d'=' -f2)
SENDGRID_KEY=$(grep SENDGRID_API_KEY .env | cut -d'=' -f2)
DEFAULT_FROM_EMAIL=$(grep DEFAULT_FROM_EMAIL .env | cut -d'=' -f2)
PAYPAL_CLIENT_ID=$(grep PAYPAL_CLIENT_ID .env | cut -d'=' -f2)
PAYPAL_SECRET=$(grep PAYPAL_SECRET .env | cut -d'=' -f2)

# Build and push Docker image
echo "Building and pushing Docker image..."
docker build -t $IMAGE_NAME .
gcloud auth configure-docker
docker push $IMAGE_NAME

# Create or update secrets
echo "Setting up secrets..."
for SECRET_NAME in django-secret-key postgres-password sendgrid-api-key paypal-client-id paypal-secret; do
  gcloud secrets describe $SECRET_NAME > /dev/null 2>&1 || \
  gcloud secrets create $SECRET_NAME --replication-policy="automatic"
done

# Set secret values
echo -n "$DB_PASSWORD" | gcloud secrets versions add postgres-password --data-file=-
echo -n "$SENDGRID_KEY" | gcloud secrets versions add sendgrid-api-key --data-file=-
echo -n "$PAYPAL_CLIENT_ID" | gcloud secrets versions add paypal-client-id --data-file=-
echo -n "$PAYPAL_SECRET" | gcloud secrets versions add paypal-secret --data-file=-

# Create and configure storage bucket
echo "Setting up storage bucket..."
gsutil ls -b gs://$BUCKET_NAME > /dev/null 2>&1 || gsutil mb -l $REGION gs://$BUCKET_NAME
gsutil iam ch allUsers:objectViewer gs://$BUCKET_NAME

# Deploy to Cloud Run
echo "Deploying to Cloud Run..."
gcloud run deploy $SERVICE_NAME \
  --image $IMAGE_NAME \
  --platform managed \
  --region $REGION \
  --allow-unauthenticated \
  --startup-cpu-boost \
  --cpu 1 \
  --memory 1Gi \
  --timeout 30m \
  --mount type=cloud-storage,bucket=$BUCKET_NAME,path=/app/media \
  --set-env-vars="ALLOWED_HOSTS=.run.app,$SERVICE_NAME.run.app,\
SENDGRID_SANDBOX_MODE=False,\
DB_USER=postgres,\
DB_NAME=postgres,\
DB_HOST=/cloudsql/$INSTANCE_CONNECTION_NAME,\
DEFAULT_FROM_EMAIL=$DEFAULT_FROM_EMAIL" \
  --set-secrets="DJANGO_SECRET_KEY=django-secret-key:latest,\
DB_PASSWORD=postgres-password:latest,\
AWS_ACCESS_KEY_ID=aws-access-key:latest,\
AWS_SECRET_ACCESS_KEY=aws-secret-key:latest,\
SENDGRID_API_KEY=sendgrid-api-key:latest,\
PAYPAL_CLIENT_ID=paypal-client-id:latest,\
PAYPAL_SECRET=paypal-secret:latest" \
  --add-cloudsql-instances=$INSTANCE_CONNECTION_NAME

echo "Deployment complete!"