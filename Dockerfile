FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8080
ENV DJANGO_SECRET_KEY=dev-secret-key-change-in-production
ENV DEBUG=True
ENV ALLOWED_HOSTS=localhost,127.0.0.1

# Set work directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project and entrypoint script
COPY . .

# Copy service account credentials for local testing
COPY database-bucket.json /app/database-bucket.json
ENV GOOGLE_APPLICATION_CREDENTIALS=/app/database-bucket.json

# Ensure entrypoint script is executable
RUN chmod +x /app/entrypoint.sh

# Collect static files
RUN python manage.py collectstatic --noinput

# Expose the port
EXPOSE 8080

# Use entrypoint script
CMD ["./entrypoint.sh"]