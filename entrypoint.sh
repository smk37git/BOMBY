#!/bin/bash

# Wait for PostgreSQL...
if [ -n "$DB_HOST" ]; then
  echo "Waiting for PostgreSQL..."
  until pg_isready -h ${DB_HOST#/cloudsql/} -U $DB_USER 2>/dev/null; do
    sleep 2
  done
  echo "Database connection established!"
fi

# Mount GCS bucket with proper options
echo "Mounting GCS bucket..."
gcsfuse --implicit-dirs -o allow_other $BUCKET_NAME /app/media || echo "Bucket mounting failed, continuing anyway"

# Create required directories
mkdir -p /app/media/profile_pictures
chmod -R 777 /app/media

# Run migrations
python manage.py migrate

# Start the server
gunicorn mywebsite.wsgi:application --bind 0.0.0.0:$PORT