#!/bin/bash

# Improved debugging - show environment variables (sanitized)
echo "Running with environment variables:"
echo "DB_HOST: ${DB_HOST:-not set}"
echo "DB_USER: ${DB_USER:-not set}"
echo "K_SERVICE: ${K_SERVICE:-not set}"
echo "DEBUG: ${DEBUG:-not set}"
echo "ALLOWED_HOSTS: ${ALLOWED_HOSTS:-not set}"
# Don't print secrets or passwords

# Improved Cloud SQL connection handling
if [[ "$DB_HOST" == /cloudsql/* ]]; then
  echo "Using Cloud SQL socket connection..."
  # For Cloud SQL, we can't use pg_isready directly with socket
  # So we'll just wait a moment for the proxy to be ready
  sleep 5
  echo "Proceeding with Cloud SQL connection via socket"
else
  echo "Waiting for PostgreSQL..."
  until pg_isready -h $DB_HOST -U $DB_USER 2>/dev/null; do
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
  
  # Make sure the directories are writable by the application user
  chmod -R 777 /app/media
  
  # On Cloud Run, we run as non-root so use proper permissions
  if [ -n "$K_SERVICE" ]; then
    chown -R 1000:1000 /app/media
  else
    chown -R nobody:nogroup /app/media
  fi
  
  # Display permissions for debugging
  echo "Media directory permissions:"
  ls -la /app/media
fi

# Run migrations
echo "Running migrations..."
python manage.py migrate --noinput

# Collect static files again to be sure (with better error handling)
echo "Collecting static files..."
python manage.py collectstatic --noinput --clear || {
  echo "Error collecting static files, but continuing anyway"
}

echo "Starting Gunicorn server..."
exec gunicorn mywebsite.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --timeout 120 --access-logfile - --error-logfile -