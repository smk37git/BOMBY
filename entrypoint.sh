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

# Mount GCS bucket
echo "Mounting GCS bucket..."
gcsfuse --implicit-dirs $BUCKET_NAME /app/media || echo "Bucket mounting failed, continuing anyway"

# Run migrations
python manage.py migrate

# Start the server
gunicorn mywebsite.wsgi:application --bind 0.0.0.0:$PORT