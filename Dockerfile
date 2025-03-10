FROM python:3.11-slim

# Install PostgreSQL client and gcsfuse
RUN apt-get update && apt-get install -y postgresql-client lsb-release curl gnupg && \
    echo "deb http://packages.cloud.google.com/apt gcsfuse-$(lsb_release -c -s) main" | tee /etc/apt/sources.list.d/gcsfuse.list && \
    curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | apt-key add - && \
    apt-get update && apt-get install -y gcsfuse

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

# Ensure entrypoint script is executable
RUN chmod +x /app/entrypoint.sh

# Create static directory and collect static files with fallback
RUN mkdir -p /tmp/staticfiles && \
    python manage.py collectstatic --noinput || echo "Static collection failed, continuing anyway"

# Expose the port
EXPOSE 8080

# Use entrypoint script
CMD ["./entrypoint.sh"]