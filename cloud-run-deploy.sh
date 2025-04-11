#!/bin/bash

# Exit on any error
set -e

# Configuration
PROJECT_ID="premium-botany-453018-a0"
SERVICE_NAME="bomby"
REGION="us-central1"
IMAGE_NAME="gcr.io/$PROJECT_ID/$SERVICE_NAME"
INSTANCE_CONNECTION_NAME="$PROJECT_ID:$REGION:bomby-database"
DB_NAME="postgres"
DB_USER="postgres"
DB_PASSWORD=$(grep DB_PASSWORD .env | cut -d'=' -f2)
SENDGRID_KEY=$(grep SENDGRID_API_KEY .env | cut -d'=' -f2)
DEFAULT_FROM_EMAIL=$(grep DEFAULT_FROM_EMAIL .env | cut -d'=' -f2)
PAYPAL_CLIENT_ID=$(grep PAYPAL_CLIENT_ID .env | cut -d'=' -f2)
PAYPAL_SECRET=$(grep PAYPAL_SECRET .env | cut -d'=' -f2)
BUCKET_NAME="bomby-user-uploads"

# Build the Docker image
echo "Building Docker image..."
docker build -t $IMAGE_NAME .

# Configure Docker to use gcloud as a credential helper
echo "Configuring Docker authentication..."
gcloud auth configure-docker

# Push the image to Google Container Registry
echo "Pushing image to Google Container Registry..."
docker push $IMAGE_NAME

# Create secrets
echo "Setting up secrets..."

# Existing secrets
gcloud secrets describe django-secret-key > /dev/null 2>&1 || \
gcloud secrets create django-secret-key --replication-policy="automatic"

gcloud secrets describe postgres-password > /dev/null 2>&1 || \
gcloud secrets create postgres-password --replication-policy="automatic" --data-file=<(echo -n "$DB_PASSWORD")

gcloud secrets describe sendgrid-api-key > /dev/null 2>&1 || \
gcloud secrets create sendgrid-api-key --replication-policy="automatic" --data-file=<(echo -n "$SENDGRID_KEY")

# PayPal secrets
gcloud secrets describe paypal-client-id > /dev/null 2>&1 || \
gcloud secrets create paypal-client-id --replication-policy="automatic" --data-file=<(echo -n "$PAYPAL_CLIENT_ID")

gcloud secrets describe paypal-secret > /dev/null 2>&1 || \
gcloud secrets create paypal-secret --replication-policy="automatic" --data-file=<(echo -n "$PAYPAL_SECRET")

# Ensure the bucket exists
echo "Ensuring the storage bucket exists..."
gsutil ls -b gs://$BUCKET_NAME > /dev/null 2>&1 || \
gsutil mb -l $REGION gs://$BUCKET_NAME

# Configure bucket permissions
echo "Setting bucket permissions..."

# First disable uniform bucket-level access to allow fine-grained control
gsutil uniformbucketlevelaccess set off gs://$BUCKET_NAME

# Remove any existing all-user permissions
gsutil iam ch -d allUsers:objectViewer gs://$BUCKET_NAME 2>/dev/null || true

# Grant public access only to profile_pictures folder
gsutil -m acl ch -r -u AllUsers:R gs://$BUCKET_NAME/profile_pictures

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
  --set-env-vars="DEBUG=False,ALLOWED_HOSTS=bomby.us,www.bomby.us,.run.app,$SERVICE_NAME.run.app,SENDGRID_SANDBOX_MODE=False,DB_NAME=$DB_NAME,DB_USER=$DB_USER,DB_HOST=/cloudsql/$INSTANCE_CONNECTION_NAME" \
  --set-secrets="DJANGO_SECRET_KEY=django-secret-key:latest,DB_PASSWORD=postgres-password:latest,AWS_ACCESS_KEY_ID=aws-access-key:latest,AWS_SECRET_ACCESS_KEY=aws-secret-key:latest,SENDGRID_API_KEY=sendgrid-api-key:latest,DEFAULT_FROM_EMAIL=default-from-email:latest,PAYPAL_CLIENT_ID=paypal-client-id:latest,PAYPAL_SECRET=paypal-secret:latest" \
  --add-cloudsql-instances=$INSTANCE_CONNECTION_NAME

echo "Deployment complete! Your website should be available soon at the URL above."