FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8080
ENV DJANGO_SECRET_KEY=dev-secret-key-change-in-production
ENV DEBUG=True
ENV ALLOWED_HOSTS=localhost,127.0.0.1,.run.app
ENV STATIC_URL=/static/
ENV STATIC_ROOT=/app/staticfiles

# Set work directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install additional packages for serving static files
RUN apt-get update && apt-get install -y --no-install-recommends \
    nginx \
    && rm -rf /var/lib/apt/lists/*

# Copy project
COPY . .

# Create media directory if it doesn't exist
RUN mkdir -p ACCOUNTS/static/media

# Collect static files
RUN python manage.py collectstatic --noinput
RUN chmod -R 755 /app/staticfiles

# Make the check_static.py script executable
RUN chmod +x /app/check_static.py
RUN python /app/check_static.py

# Configure Nginx to serve static files
COPY nginx.conf /etc/nginx/sites-available/default
RUN ln -sf /etc/nginx/sites-available/default /etc/nginx/sites-enabled/default

# Expose the port
EXPOSE 8080

# Start Nginx and Gunicorn
CMD service nginx start && exec gunicorn mywebsite.wsgi:application --bind 0.0.0.0:$PORT