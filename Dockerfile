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
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . .

# Create media directory if it doesn't exist
RUN mkdir -p ACCOUNTS/static/media

# Collect static files
RUN python manage.py collectstatic --noinput

# After the collectstatic command in Dockerfile
RUN cp -r MAIN/static/* staticfiles/ || true
RUN cp -r ACCOUNTS/static/* staticfiles/ || true
RUN cp -r PORTFOLIO/static/* staticfiles/ || true

# Expose the port
EXPOSE 8080

# Start Gunicorn
CMD exec gunicorn mywebsite.wsgi:application --bind 0.0.0.0:$PORT