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

# Run migrations
python manage.py migrate

# After migrations
if [ ! -f /tmp/data_imported ]; then
  echo "Importing data..."
  gsutil cp gs://bomby-user-data/data.json /tmp/
  python manage.py loaddata /tmp/data.json
  touch /tmp/data_imported
fi

# Start the server
gunicorn mywebsite.wsgi:application --bind 0.0.0.0:$PORT