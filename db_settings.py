# Add this to your mywebsite/settings.py file to securely connect to Cloud SQL

import os
from pathlib import Path

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent / '.env.prod')

# Database
# https://docs.djangoproject.com/en/5.1/ref/settings/#databases

# Check if running on Google Cloud Run
if os.environ.get('CLOUD_RUN', False):
    # Running on Cloud Run, use Unix socket
    DATABASES = {
        'default': {
            'ENGINE': os.environ.get('DB_ENGINE', 'django.db.backends.postgresql'),
            'NAME': os.environ.get('DB_NAME', 'bomby_db'),
            'USER': os.environ.get('DB_USER', 'bomby_user'),
            'PASSWORD': os.environ.get('DB_PASSWORD', ''),
            'HOST': os.environ.get('DB_HOST', '/cloudsql/your-gcp-project-id:us-central1:bomby-db-instance'),
            'PORT': os.environ.get('DB_PORT', '5432'),
        }
    }
else:
    # Local development - use either local PostgreSQL or SQLite
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# Security settings
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'your-default-secret-key-for-development')
DEBUG = os.environ.get('DEBUG', 'False') == 'True'
ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', '*').split(',')

# HTTPS settings
SECURE_SSL_REDIRECT = not DEBUG
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True 