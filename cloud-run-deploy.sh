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
BUCKET_NAME="bomby-user-uploads"

# Firebase Configuration
FIREBASE_API_KEY=$(grep FIREBASE_API_KEY .env | cut -d'=' -f2)
FIREBASE_AUTH_DOMAIN=$(grep FIREBASE_AUTH_DOMAIN .env | cut -d'=' -f2)
FIREBASE_PROJECT_ID=$(grep FIREBASE_PROJECT_ID .env | cut -d'=' -f2)
FIREBASE_STORAGE_BUCKET=$(grep FIREBASE_STORAGE_BUCKET .env | cut -d'=' -f2)
FIREBASE_MESSAGING_SENDER_ID=$(grep FIREBASE_MESSAGING_SENDER_ID .env | cut -d'=' -f2)
FIREBASE_APP_ID=$(grep FIREBASE_APP_ID .env | cut -d'=' -f2)

# Build the Docker image
echo "Building Docker image..."
docker build -t $IMAGE_NAME .

# Configure Docker to use gcloud as a credential helper
echo "Configuring Docker authentication..."
gcloud auth configure-docker

# Push the image to Google Container Registry
echo "Pushing image to Google Container Registry..."
docker push $IMAGE_NAME

# Create or update Firebase secrets
echo "Ensuring Firebase secrets exist..."

# Ensure firebase-credentials secret exists (the service account JSON file)
gcloud secrets describe firebase-credentials-json > /dev/null 2>&1 || \
gcloud secrets create firebase-credentials-json --replication-policy="automatic"

gcloud secrets describe firebase-api-key > /dev/null 2>&1 || \
gcloud secrets create firebase-api-key --replication-policy="automatic" --data-file=<(echo -n "$FIREBASE_API_KEY")

gcloud secrets describe firebase-auth-domain > /dev/null 2>&1 || \
gcloud secrets create firebase-auth-domain --replication-policy="automatic" --data-file=<(echo -n "$FIREBASE_AUTH_DOMAIN")

gcloud secrets describe firebase-project-id > /dev/null 2>&1 || \
gcloud secrets create firebase-project-id --replication-policy="automatic" --data-file=<(echo -n "$FIREBASE_PROJECT_ID")

gcloud secrets describe firebase-storage-bucket > /dev/null 2>&1 || \
gcloud secrets create firebase-storage-bucket --replication-policy="automatic" --data-file=<(echo -n "$FIREBASE_STORAGE_BUCKET")

gcloud secrets describe firebase-messaging-sender-id > /dev/null 2>&1 || \
gcloud secrets create firebase-messaging-sender-id --replication-policy="automatic" --data-file=<(echo -n "$FIREBASE_MESSAGING_SENDER_ID")

gcloud secrets describe firebase-app-id > /dev/null 2>&1 || \
gcloud secrets create firebase-app-id --replication-policy="automatic" --data-file=<(echo -n "$FIREBASE_APP_ID")

# Other secrets
gcloud secrets describe django-secret-key > /dev/null 2>&1 || \
gcloud secrets create django-secret-key --replication-policy="automatic"

gcloud secrets describe postgres-password > /dev/null 2>&1 || \
gcloud secrets create postgres-password --replication-policy="automatic" --data-file=<(echo -n "$DB_PASSWORD")

gcloud secrets describe sendgrid-api-key > /dev/null 2>&1 || \
gcloud secrets create sendgrid-api-key --replication-policy="automatic" --data-file=<(echo -n "$SENDGRID_KEY")

# Ensure the bucket exists with correct permissions
echo "Ensuring the storage bucket exists..."
gsutil ls -b gs://$BUCKET_NAME > /dev/null 2>&1 || \
gsutil mb -l $REGION gs://$BUCKET_NAME

# Make bucket publicly readable
gsutil iam ch allUsers:objectViewer gs://$BUCKET_NAME

# Deploy to Cloud Run
echo "Deploying to Cloud Run..."
gcloud run deploy $SERVICE_NAME \
  --image $IMAGE_NAME \
  --platform managed \
  --region $REGION \
  --allow-unauthenticated \
  --mount type=cloud-storage,bucket=$BUCKET_NAME,path=/app/media \
  --set-env-vars="DEBUG=False,\
ALLOWED_HOSTS=.run.app,$SERVICE_NAME.run.app,\
SENDGRID_SANDBOX_MODE=False,\
DB_NAME=$DB_NAME,\
DB_USER=$DB_USER,\
FIREBASE_CREDENTIALS_PATH=/app/firebase/firebase-credentials.json,\
DB_HOST=/cloudsql/$INSTANCE_CONNECTION_NAME" \
  --set-secrets="DJANGO_SECRET_KEY=django-secret-key:latest,\
DB_PASSWORD=postgres-password:latest,\
AWS_ACCESS_KEY_ID=aws-access-key:latest,\
AWS_SECRET_ACCESS_KEY=aws-secret-key:latest,\
/app/firebase/firebase-credentials.json=firebase-credentials-json:latest,\
FIREBASE_API_KEY=firebase-api-key:latest,\
FIREBASE_AUTH_DOMAIN=firebase-auth-domain:latest,\
FIREBASE_PROJECT_ID=firebase-project-id:latest,\
FIREBASE_STORAGE_BUCKET=firebase-storage-bucket:latest,\
FIREBASE_MESSAGING_SENDER_ID=firebase-messaging-sender-id:latest,\
FIREBASE_APP_ID=firebase-app-id:latest,\
SENDGRID_API_KEY=sendgrid-api-key:latest,\
DEFAULT_FROM_EMAIL=default-from-email:latest" \
  --memory 512Mi \
  --add-cloudsql-instances=$INSTANCE_CONNECTION_NAME

echo "Deployment complete! Your website should be available soon at the URL above."