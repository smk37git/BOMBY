#!/bin/bash

# Run migrations
python manage.py migrate

# Create a trap to backup the database on exit
backup_db() {
  echo "Backing up database..."
  gsutil cp db.sqlite3 gs://$GS_BUCKET_NAME/db.sqlite3
  echo "Database backup complete."
}
trap backup_db EXIT

# Start the server
gunicorn mywebsite.wsgi:application --bind 0.0.0.0:$PORT