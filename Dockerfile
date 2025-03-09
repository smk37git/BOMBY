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

# Create media directory if it doesn't exist
RUN mkdir -p ACCOUNTS/static/media

# Collect static files
RUN python manage.py collectstatic --noinput

# Make entrypoint script executable
RUN chmod +x entrypoint.sh

# Expose the port
EXPOSE 8080

# Use entrypoint script
CMD ["./entrypoint.sh"]