#!/bin/bash
set -e

# Configuration
PROJECT_ID="premium-botany-453018-a0"
SERVICE_NAME="bomby"
REGION="us-central1"
IMAGE_NAME="gcr.io/$PROJECT_ID/$SERVICE_NAME"
INSTANCE_CONNECTION_NAME="$PROJECT_ID:$REGION:bomby-database"
BUCKET_NAME="bomby-user-uploads"

echo "Loading secrets from .env..."
# Load all secrets from .env
DJANGO_SECRET_KEY=$(grep DJANGO_SECRET_KEY .env | cut -d'=' -f2)
DB_PASSWORD=$(grep DB_PASSWORD .env | cut -d'=' -f2)
EMAIL_HOST_USER=$(grep EMAIL_HOST_USER .env | cut -d'=' -f2)
EMAIL_HOST_PASSWORD=$(grep EMAIL_HOST_PASSWORD .env | cut -d'=' -f2)
DEFAULT_FROM_EMAIL=$(grep DEFAULT_FROM_EMAIL .env | cut -d'=' -f2)
ADMIN_VERIFICATION_CODE=$(grep ADMIN_VERIFICATION_CODE .env | cut -d'=' -f2 | tr -d ' "')
AWS_ACCESS_KEY_ID=$(grep AWS_ACCESS_KEY_ID .env | cut -d'=' -f2)
AWS_SECRET_ACCESS_KEY=$(grep AWS_SECRET_ACCESS_KEY .env | cut -d'=' -f2)
PAYPAL_CLIENT_ID=$(grep PAYPAL_CLIENT_ID .env | cut -d'=' -f2)
PAYPAL_SECRET=$(grep PAYPAL_SECRET .env | cut -d'=' -f2)
GOOGLE_CLIENT_ID=$(grep GOOGLE_CLIENT_ID .env | cut -d'=' -f2)
GOOGLE_CLIENT_SECRET=$(grep GOOGLE_CLIENT_SECRET .env | cut -d'=' -f2)
ANTHROPIC_API_KEY=$(grep ANTHROPIC_API_KEY .env | cut -d'=' -f2)
FUZEOBS_SECRET_KEY=$(grep FUZEOBS_SECRET_KEY .env | cut -d'=' -f2)
TWITCH_CLIENT_ID=$(grep TWITCH_CLIENT_ID .env | cut -d'=' -f2)
TWITCH_CLIENT_SECRET=$(grep TWITCH_CLIENT_SECRET .env | cut -d'=' -f2)
TWITCH_WEBHOOK_SECRET=$(grep TWITCH_WEBHOOK_SECRET .env | cut -d'=' -f2)
SCHEDULER_SECRET=$(grep SCHEDULER_SECRET .env | cut -d'=' -f2)
YOUTUBE_CLIENT_ID=$(grep YOUTUBE_CLIENT_ID .env | cut -d'=' -f2)
YOUTUBE_CLIENT_SECRET=$(grep YOUTUBE_CLIENT_SECRET .env | cut -d'=' -f2)
KICK_CLIENT_ID=$(grep KICK_CLIENT_ID .env | cut -d'=' -f2)
KICK_CLIENT_SECRET=$(grep KICK_CLIENT_SECRET .env | cut -d'=' -f2)
STRIPE_PUBLISHABLE_KEY=$(grep STRIPE_PUBLISHABLE_KEY .env | cut -d'=' -f2)
STRIPE_SECRET_KEY=$(grep STRIPE_SECRET_KEY .env | cut -d'=' -f2)
STRIPE_WEBHOOK_SECRET=$(grep STRIPE_SECRET_KEY .env | cut -d'=' -f2)

# Build and push Docker image
echo "Building and pushing Docker image..."
docker build -t $IMAGE_NAME .
gcloud auth configure-docker
docker push $IMAGE_NAME

# Create all secrets if they don't exist
echo "Setting up secrets in Google Secret Manager..."
SECRETS=(
  "django-secret-key"
  "postgres-password"
  "email-host-user"
  "email-host-password"
  "admin-verification-code"
  "aws-access-key"
  "aws-secret-key"
  "paypal-client-id"
  "paypal-secret"
  "google-client-id"
  "google-client-secret"
  "anthropic-api-key"
  "fuzeobs-secret-key"
  "twitch-client-id"
  "twitch-client-secret"
  "twitch-webhook-secret"
  "scheduler-secret"
  "youtube-client-id"
  "youtube-client-secret"
  "kick-client-id"
  "kick-client-secret"
  "stripe-publishable-key"
  "stripe-secret-key"
  "stripe-webhook-secret"
)

for SECRET_NAME in "${SECRETS[@]}"; do
  gcloud secrets describe $SECRET_NAME > /dev/null 2>&1 || \
  gcloud secrets create $SECRET_NAME --replication-policy="automatic"
done

# Update all secret values
echo "Updating secret values..."
echo -n "$DJANGO_SECRET_KEY" | gcloud secrets versions add django-secret-key --data-file=-
echo -n "$DB_PASSWORD" | gcloud secrets versions add postgres-password --data-file=-
echo -n "$EMAIL_HOST_USER" | gcloud secrets versions add email-host-user --data-file=-
echo -n "$EMAIL_HOST_PASSWORD" | gcloud secrets versions add email-host-password --data-file=-
echo -n "$ADMIN_VERIFICATION_CODE" | gcloud secrets versions add admin-verification-code --data-file=-
echo -n "$AWS_ACCESS_KEY_ID" | gcloud secrets versions add aws-access-key --data-file=-
echo -n "$AWS_SECRET_ACCESS_KEY" | gcloud secrets versions add aws-secret-key --data-file=-
echo -n "$PAYPAL_CLIENT_ID" | gcloud secrets versions add paypal-client-id --data-file=-
echo -n "$PAYPAL_SECRET" | gcloud secrets versions add paypal-secret --data-file=-
echo -n "$GOOGLE_CLIENT_ID" | gcloud secrets versions add google-client-id --data-file=-
echo -n "$GOOGLE_CLIENT_SECRET" | gcloud secrets versions add google-client-secret --data-file=-
echo -n "$ANTHROPIC_API_KEY" | gcloud secrets versions add anthropic-api-key --data-file=-
echo -n "$FUZEOBS_SECRET_KEY" | gcloud secrets versions add fuzeobs-secret-key --data-file=-
echo -n "$TWITCH_CLIENT_ID" | gcloud secrets versions add twitch-client-id --data-file=-
echo -n "$TWITCH_CLIENT_SECRET" | gcloud secrets versions add twitch-client-secret --data-file=-
echo -n "$TWITCH_WEBHOOK_SECRET" | gcloud secrets versions add twitch-webhook-secret --data-file=-
echo -n "$SCHEDULER_SECRET" | gcloud secrets versions add scheduler-secret --data-file=-
echo -n "$YOUTUBE_CLIENT_ID" | gcloud secrets versions add youtube-client-id --data-file=-
echo -n "$YOUTUBE_CLIENT_SECRET" | gcloud secrets versions add youtube-client-secret --data-file=-
echo -n "$KICK_CLIENT_ID" | gcloud secrets versions add kick-client-id --data-file=-
echo -n "$KICK_CLIENT_SECRET" | gcloud secrets versions add kick-client-secret --data-file=-
echo -n "$STRIPE_PUBLISHABLE_KEY" | gcloud secrets versions add stripe-publishable-key --data-file=-
echo -n "$STRIPE_SECRET_KEY" | gcloud secrets versions add stripe-secret-key --data-file=-
echo -n "$STRIPE_WEBHOOK_SECRET" | gcloud secrets versions add stripe-webhook-secret --data-file=-

# Set up storage bucket
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
  --set-env-vars="DEBUG=False,\
ALLOWED_HOSTS=bomby.us,www.bomby.us,bomby-799218251279.us-central1.run.app,\
DB_USER=postgres,\
DB_NAME=postgres,\
DB_HOST=/cloudsql/$INSTANCE_CONNECTION_NAME,\
DEFAULT_FROM_EMAIL=$DEFAULT_FROM_EMAIL,\
ENABLE_IMAGE_MODERATION=True,\
IMAGE_MODERATION_CONFIDENCE_THRESHOLD=99.0,\
AWS_REGION=us-east-1" \
  --set-secrets="DJANGO_SECRET_KEY=django-secret-key:latest,\
DB_PASSWORD=postgres-password:latest,\
EMAIL_HOST_USER=email-host-user:latest,\
EMAIL_HOST_PASSWORD=email-host-password:latest,\
ADMIN_VERIFICATION_CODE=admin-verification-code:latest,\
AWS_ACCESS_KEY_ID=aws-access-key:latest,\
AWS_SECRET_ACCESS_KEY=aws-secret-key:latest,\
PAYPAL_CLIENT_ID=paypal-client-id:latest,\
PAYPAL_SECRET=paypal-secret:latest,\
GOOGLE_CLIENT_ID=google-client-id:latest,\
GOOGLE_CLIENT_SECRET=google-client-secret:latest,\
ANTHROPIC_API_KEY=anthropic-api-key:latest,\
FUZEOBS_SECRET_KEY=fuzeobs-secret-key:latest,\
TWITCH_CLIENT_ID=twitch-client-id:latest,\
TWITCH_CLIENT_SECRET=twitch-client-secret:latest,\
TWITCH_WEBHOOK_SECRET=twitch-webhook-secret:latest,\
SCHEDULER_SECRET=scheduler-secret:latest,\
YOUTUBE_CLIENT_ID=youtube-client-id:latest,\
YOUTUBE_CLIENT_SECRET=youtube-client-secret:latest,\
KICK_CLIENT_ID=kick-client-id:latest,\
KICK_CLIENT_SECRET=kick-client-secret:latest,\
STRIPE_PUBLISHABLE_KEY=stripe-publishable-key:latest,\
STRIPE_SECRET_KEY=stripe-secret-key:latest, \
STRIPE_WEBHOOK_SECRET=stripe-webhook_secret:latest" \
  --add-cloudsql-instances=$INSTANCE_CONNECTION_NAME

echo ""
echo "Deployment complete!"
echo ""