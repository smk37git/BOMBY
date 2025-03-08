# BOMBY Website - Google Cloud Run Deployment

This repository contains the code for the BOMBY website and instructions for deploying it to Google Cloud Run using Docker.

## Prerequisites

1. [Google Cloud SDK](https://cloud.google.com/sdk/docs/install) installed and configured
2. [Docker](https://docs.docker.com/get-docker/) installed
3. A Google Cloud Platform account with billing enabled
4. A Google Cloud project created

## Local Development

1. Clone this repository
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Run migrations:
   ```
   python manage.py migrate
   ```
4. Start the development server:
   ```
   python manage.py runserver
   ```

## Deploying to Google Cloud Run

### Option 1: Using the Deployment Script

1. Edit the `cloud-run-deploy.sh` script and update the following variables:
   - `PROJECT_ID`: Your Google Cloud project ID
   - `SERVICE_NAME`: Name for your Cloud Run service
   - `REGION`: Google Cloud region (e.g., us-central1)

2. Make the script executable:
   ```
   chmod +x cloud-run-deploy.sh
   ```

3. Run the deployment script:
   ```
   ./cloud-run-deploy.sh
   ```

### Option 2: Manual Deployment

1. Build the Docker image:
   ```
   docker build -t gcr.io/[PROJECT_ID]/bomby-website .
   ```

2. Configure Docker to use gcloud as a credential helper:
   ```
   gcloud auth configure-docker
   ```

3. Push the image to Google Container Registry:
   ```
   docker push gcr.io/[PROJECT_ID]/bomby-website
   ```

4. Deploy to Cloud Run:
   ```
   gcloud run deploy bomby-website \
     --image gcr.io/[PROJECT_ID]/bomby-website \
     --platform managed \
     --region us-central1 \
     --allow-unauthenticated \
     --set-env-vars="DEBUG=False" \
     --memory 512Mi
   ```

## Important Notes

1. The Dockerfile is configured to use Gunicorn as the WSGI server.
2. Static files are collected during the Docker build process.
3. Database migrations are commented out in the Dockerfile - you may need to run them manually or uncomment that line depending on your deployment strategy.
4. For production, you should set up a proper database (like Cloud SQL) instead of SQLite.
5. Consider setting up Cloud Storage for serving static and media files.

## Environment Variables

You can set environment variables in the Cloud Run deployment command:

```
--set-env-vars="KEY1=VALUE1,KEY2=VALUE2"
```

Common variables to set:
- `DEBUG=False`
- `SECRET_KEY=your-secret-key`
- `DATABASE_URL=your-database-url`
- `ALLOWED_HOSTS=.run.app,your-domain.com` 