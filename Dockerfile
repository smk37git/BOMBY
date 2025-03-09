FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8080
ENV DJANGO_SECRET_KEY=dev-secret-key-change-in-production
ENV DEBUG=False
ENV ALLOWED_HOSTS=localhost,127.0.0.1,.run.app
ENV STATIC_URL=/static/
ENV STATIC_ROOT=/app/staticfiles

# Set work directory
WORKDIR /app

# Install dependencies and SQLite
RUN apt-get update && apt-get install -y sqlite3 && apt-get clean

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt firebase-admin

# Create data directory for persistent storage
RUN mkdir -p /app/data

# Copy project
COPY . .

# Update database path to use the data directory
RUN sed -i "s|BASE_DIR / 'db.sqlite3'|os.path.join(BASE_DIR, 'data', 'db.sqlite3')|g" mywebsite/settings.py

# Create media directory if it doesn't exist
RUN mkdir -p ACCOUNTS/static/media

# Collect static files
RUN python manage.py collectstatic --noinput

# Create a startup script that handles migrations and database initialization
RUN echo '#!/bin/bash\n\
# Check if database directory exists and is writable\n\
if [ ! -d "/app/data" ]; then\n\
    mkdir -p /app/data\n\
fi\n\
\n\
# Make sure permissions are correct\n\
chmod -R 777 /app/data\n\
\n\
# Initialize database if it doesn't exist\n\
if [ ! -f "/app/data/db.sqlite3" ]; then\n\
    echo "Initializing database..."\n\
    python manage.py migrate --noinput\n\
else\n\
    # Apply migrations to existing database\n\
    echo "Applying migrations..."\n\
    python manage.py migrate --noinput\n\
fi\n\
\n\
# Start Gunicorn\n\
echo "Starting Gunicorn..."\n\
exec gunicorn mywebsite.wsgi:application --bind 0.0.0.0:$PORT --timeout 120\n\
' > /app/start.sh && chmod +x /app/start.sh

# Expose the port
EXPOSE 8080

# Start using the script that includes migrations
CMD ["/app/start.sh"]