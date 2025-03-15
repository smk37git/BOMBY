#!/bin/bash

set -e

# Wait for PostgreSQL
if [ -n "$DB_HOST" ]; then
  echo "Waiting for PostgreSQL..."
  until pg_isready -h ${DB_HOST#/cloudsql/} -U $DB_USER 2>/dev/null; do
    echo "Database connection not available, waiting..."
    sleep 2
  done
  echo "Database connection established!"
fi

# Check if running in Cloud Run with mounted bucket
if [ -d "/app/media" ]; then
  echo "Preparing media directories..."
  # Create necessary directories
  mkdir -p /app/media/profile_pictures
  
  # Make sure the directories are writable
  chmod -R 777 /app/media
  chown -R nobody:nogroup /app/media
  
  # Display permissions for debugging
  echo "Media directory permissions:"
  ls -la /app/media
fi

# Run migrations
python manage.py migrate

# Create products (ONE TIME)
python create_products.py

python manage.py collectstatic --noinput --clear

# Start the server
gunicorn mywebsite.wsgi:application --bind 0.0.0.0:$PORT