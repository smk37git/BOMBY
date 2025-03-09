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

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt whitenoise

# Copy project
COPY . .

# Create media directory if it doesn't exist
RUN mkdir -p ACCOUNTS/static/media

# Collect static files
RUN python manage.py collectstatic --noinput

# Create a startup script that handles migrations
RUN echo '#!/bin/bash\n\
# Apply database migrations\n\
python manage.py migrate --noinput\n\
\n\
# Start Gunicorn\n\
exec gunicorn mywebsite.wsgi:application --bind 0.0.0.0:$PORT\n\
' > /app/start.sh && chmod +x /app/start.sh

# Test WhiteNoise configuration
RUN chmod +x /app/test_whitenoise.py
RUN python /app/test_whitenoise.py

# Expose the port
EXPOSE 8080

# Start using the script that includes migrations
CMD ["/app/start.sh"]