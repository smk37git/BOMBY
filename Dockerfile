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

# Copy project
COPY . .

# Copy service account credentials for local testing
COPY database-bucket.json /app/database-bucket.json
ENV GOOGLE_APPLICATION_CREDENTIALS=/app/database-bucket.json

# Copy backup script if it exists (will be created by deploy script)
ARG BACKUP_SCRIPT=""
ARG ENTRYPOINT_WRAPPER=""
COPY ${BACKUP_SCRIPT} /app/backup-db.sh || true
COPY ${ENTRYPOINT_WRAPPER} /app/entrypoint-wrapper.sh || true

# Collect static files
RUN python manage.py collectstatic --noinput

# Make scripts executable
RUN chmod +x entrypoint.sh
RUN if [ -f "/app/backup-db.sh" ]; then chmod +x /app/backup-db.sh; fi
RUN if [ -f "/app/entrypoint-wrapper.sh" ]; then chmod +x /app/entrypoint-wrapper.sh; fi

# Expose the port
EXPOSE 8080

# Use entrypoint script or wrapper if it exists
CMD if [ -f "/app/entrypoint-wrapper.sh" ]; then /app/entrypoint-wrapper.sh; else ./entrypoint.sh; fi