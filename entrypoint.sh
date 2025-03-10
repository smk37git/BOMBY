#!/bin/bash

# Wait for PostgreSQL to be ready (if needed)
if [ -n "$DB_HOST" ]; then
  echo "Waiting for PostgreSQL..."
  until pg_isready -h ${DB_HOST#/cloudsql/} -U $DB_USER 2>/dev/null; do
    echo "Database connection not available, waiting..."
    sleep 2
  done
  echo "Database connection established!"
fi

# Check for AWS credentials
if [ -z "$AWS_ACCESS_KEY_ID" ] || [ -z "$AWS_SECRET_ACCESS_KEY" ]; then
  echo "WARNING: AWS credentials not set. S3 storage may not work correctly."
else
  echo "AWS credentials found. Using bucket: $AWS_S3_BUCKET_NAME"
fi

# Run migrations
python manage.py migrate

# Collect static files
python manage.py collectstatic --noinput

# Start the server
gunicorn mywebsite.wsgi:application --bind 0.0.0.0:$PORT