#!/bin/bash
set -e

# Run migrations
python manage.py migrate

# Start Gunicorn
exec gunicorn mywebsite.wsgi:application --bind 0.0.0.0:$PORT --timeout 120