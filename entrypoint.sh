#!/bin/bash

# Exit on error
set -e

# Check if running in Cloud Run with mounted bucket
if [ -d "/app/media" ]; then
  echo "Preparing media directories..."
  # Create necessary directories
  mkdir -p /app/media/profile_pictures
  mkdir -p /app/media/chunk_uploads
  
  # Make sure the directories are writable
  chmod -R 777 /app/media
  chown -R nobody:nogroup /app/media
  
  # Display permissions for debugging
  echo "Media directory permissions:"
  ls -la /app/media
fi

# Run migrations
echo "Running migrations..."
python manage.py migrate --noinput

echo "Collecting static files..."
python manage.py collectstatic --noinput --clear

# Start the server with increased timeout for large uploads
echo "Starting gunicorn..."
exec gunicorn mywebsite.wsgi:application --bind 0.0.0.0:$PORT --timeout 600