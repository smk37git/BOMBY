FROM python:3.11-slim

# Install PostgreSQL client
RUN apt-get update && apt-get install -y postgresql-client && rm -rf /var/lib/apt/lists/*

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8080
ENV DJANGO_SECRET_KEY=dev-secret-key-change-in-production
ENV DEBUG=True
ENV ALLOWED_HOSTS=localhost,127.0.0.1,bomby-799218251279.us-central1.run.app
ENV USE_GCS=True
ENV GS_BUCKET_NAME=bomby-database
ENV GS_PROJECT_ID=premium-botany-453018-a0

# Set work directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project and entrypoint script
COPY . .

# Ensure entrypoint script is executable
RUN chmod +x /app/entrypoint.sh

# Collect static files
RUN python manage.py collectstatic --noinput

# Expose the port
EXPOSE 8080

# Use entrypoint script
CMD ["./entrypoint.sh"]