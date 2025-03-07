# BOMBY Django Application

## Deploying to Google Cloud Run with Secure Database

This repository contains a Django application configured for deployment to Google Cloud Run with a secure Cloud SQL database connection.

### Prerequisites

1. [Google Cloud SDK](https://cloud.google.com/sdk/docs/install) installed and configured
2. [Docker](https://docs.docker.com/get-docker/) installed
3. A Google Cloud Platform project with billing enabled
4. Enable required APIs:
   ```
   gcloud services enable cloudbuild.googleapis.com
   gcloud services enable run.googleapis.com
   gcloud services enable containerregistry.googleapis.com
   gcloud services enable secretmanager.googleapis.com
   gcloud services enable sqladmin.googleapis.com
   ```

### Secure Database Setup

1. **Create a Cloud SQL Instance**

   Run the Cloud SQL setup script:
   ```
   chmod +x cloud-sql-setup.sh
   ./cloud-sql-setup.sh
   ```

   This script will:
   - Create a PostgreSQL instance in Cloud SQL
   - Create a database and user
   - Set a secure password

2. **Set Up Secret Manager**

   Run the secrets setup script:
   ```
   chmod +x setup-secrets.sh
   ./setup-secrets.sh
   ```

   This script will:
   - Enable the Secret Manager API
   - Create secrets for your Django secret key and database password
   - Grant access to the Cloud Run service account

3. **Update Configuration**

   Edit the `cloud-run-deploy.sh` script and update the following variables:
   - `PROJECT_ID`: Your Google Cloud Project ID
   - `SERVICE_NAME`: Name for your Cloud Run service
   - `REGION`: Your preferred GCP region
   - `INSTANCE_CONNECTION_NAME`: Your Cloud SQL instance connection name

### Deployment Steps

1. **Deploy to Google Cloud Run**

   Make the deployment script executable:
   ```
   chmod +x cloud-run-deploy.sh
   ```

   Run the deployment script:
   ```
   ./cloud-run-deploy.sh
   ```

   This will:
   - Build and push your Docker image
   - Deploy to Cloud Run with Cloud SQL connection
   - Configure environment variables and secrets

2. **Run Migrations**

   After deployment, you need to run migrations on your Cloud SQL database:
   ```
   gcloud run services update bomby-django-app \
     --region=us-central1 \
     --command="python,manage.py,migrate" \
     --args="" \
     --project=your-gcp-project-id
   ```

   Then restart your service with the normal command:
   ```
   gcloud run services update bomby-django-app \
     --region=us-central1 \
     --command="" \
     --args="" \
     --project=your-gcp-project-id
   ```

### Security Best Practices

1. **Never store sensitive information in your code or Docker images**
   - Use Secret Manager for sensitive data like passwords and API keys
   - Use environment variables for non-sensitive configuration

2. **Use IAM for access control**
   - Grant minimal permissions to service accounts
   - Use service account impersonation for administrative tasks

3. **Configure SSL/TLS for database connections**
   - Cloud SQL Proxy handles this automatically

4. **Enable audit logging**
   - Monitor database access and operations
   - Set up alerts for suspicious activities

5. **Regularly update dependencies**
   - Keep your Django and other packages up to date
   - Scan for vulnerabilities using tools like Snyk or Dependabot

### Local Development with Docker

To build and run the Docker container locally:

```bash
# Build the Docker image
docker build -t bomby-django-app .

# Run the container
docker run -p 8080:8080 bomby-django-app
```

Visit http://localhost:8080 to view the application.

### Additional Resources

- [Google Cloud Run Documentation](https://cloud.google.com/run/docs)
- [Cloud SQL for PostgreSQL](https://cloud.google.com/sql/docs/postgres)
- [Secret Manager Documentation](https://cloud.google.com/secret-manager/docs)
- [Django on Cloud Run Tutorial](https://cloud.google.com/python/django/run) 