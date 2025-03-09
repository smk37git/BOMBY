#!/bin/bash

# Exit on any error
set -e

# Configuration
PROJECT_ID="premium-botany-453018-a0"
SERVICE_NAME="bomby-website"
REGION="us-central1"
IMAGE_NAME="gcr.io/$PROJECT_ID/$SERVICE_NAME"
BUCKET_NAME="bomby-user-data"  # Replace with your actual bucket name

# Create GCS bucket if it doesn't exist
echo "Ensuring GCS bucket exists..."
gsutil ls -b gs://$BUCKET_NAME > /dev/null 2>&1 || gsutil mb -l $REGION gs://$BUCKET_NAME

# Download latest database from bucket if it exists
echo "Checking for existing database in bucket..."
gsutil cp gs://$BUCKET_NAME/db.sqlite3 ./db.sqlite3 || echo "No database found in bucket"

# Apply migrations if database exists
if [ -f "./db.sqlite3" ]; then
  echo "Applying migrations to existing database..."
  python manage.py migrate
fi

# Create a backup script for the container
echo "Creating database backup script..."
cat > backup-db.sh << 'EOF'
#!/bin/bash
while true; do
  echo "[$(date)] Backing up database..."
  cp /app/db.sqlite3 /app/db.sqlite3.bak
  gsutil cp /app/db.sqlite3.bak gs://$BUCKET_NAME/db.sqlite3
  echo "[$(date)] Database backed up successfully"
  sleep 3600  # Backup every hour
done
EOF
chmod +x backup-db.sh

# Create an entrypoint wrapper to start backup process
echo "Creating entrypoint wrapper..."
cat > entrypoint-wrapper.sh << 'EOF'
#!/bin/bash
# Start the backup script in the background
nohup /app/backup-db.sh &

# Run the original entrypoint
exec /app/entrypoint.sh
EOF
chmod +x entrypoint-wrapper.sh

# Build the Docker image
echo "Building Docker image..."
docker build -t $IMAGE_NAME --build-arg BACKUP_SCRIPT=backup-db.sh --build-arg ENTRYPOINT_WRAPPER=entrypoint-wrapper.sh .

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